"""One-command incremental synchronisation (crawl + PostgreSQL import).

Runs the incremental OParl crawl (``crawl_oparl``, run recorder started but
NOT finalised) and then invokes ``pgGen``'s import against the crawl output
folder. The run row is finished with ``success=true`` and the advanced
``end_state`` only when the import exits successfully; otherwise the run is
recorded with ``success=false`` and ``end_state`` reset to the pre-crawl
baseline so the next run re-fetches the same window.

Standalone ``oparlUpdate`` keeps its own behaviour (records its own
successful run) — see design D3 of the ``incremental-oparl-sync`` change.
"""

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
import logging

from src.update.oparlUpdate import SYSTEM_URL, OUTPUT_FOLDER, crawl_oparl

logger = logging.getLogger(__name__)


def sync(system_url: str = SYSTEM_URL,
         output_folder: str = OUTPUT_FOLDER,
         last_date: str | None = None,
         recorder=None) -> int:
    """Crawl incrementally, then import the crawled JSON into PostgreSQL.

    Returns a process exit code: 0 on success, 1 when either phase failed.
    A *recorder* can be injected for tests; by default a real
    ``RunRecorder`` (DB-backed run tracking) is used.
    """
    from src.update.oparlRunLog import RunRecorder, resolve_baseline

    if recorder is None:
        recorder = RunRecorder()

    baseline, baseline_source = (
        (last_date, "--last-date override") if last_date
        else resolve_baseline(engine=recorder._engine)
    )
    logger.info("Sync baseline (%s): %s", baseline_source, baseline)

    # Phase 1: incremental crawl. The run row is started but NOT finalised —
    # the baseline may only advance after a successful import.
    try:
        crawl_oparl(system_url, baseline, recorder=recorder, finalise=False)
    except KeyboardInterrupt:
        logger.warning("Crawl interrupted (Ctrl-C); recording partial run.")
        recorder.finish(success=False)
        return 1
    except Exception as ex:  # noqa: BLE001
        logger.exception("Crawl phase failed: %s", ex)
        recorder.set_end_state(baseline)  # do not advance the baseline
        recorder.finish(success=False)
        return 1

    # Phase 2: import the crawl output into the database (pgGen upserts
    # idempotently on oparlId — safe to re-run).
    try:
        from src.pgGen import main as pggen_main
        pggen_main(output_folder)
    except SystemExit as ex:  # argparse-style failure inside pgGen
        logger.error("Import phase failed (exit %s); baseline NOT advanced.", ex.code)
        recorder.set_end_state(baseline)
        recorder.finish(success=False)
        return 1
    except Exception as ex:  # noqa: BLE001
        logger.exception("Import phase failed: %s; baseline NOT advanced.", ex)
        recorder.set_end_state(baseline)
        recorder.finish(success=False)
        return 1

    # New data landed: drop the search API's cached facet aggregates
    # (change: api-latency-optimization)
    try:
        from src.search.pgHybridSearch import invalidate_facet_cache
        invalidate_facet_cache()
        logger.info("Facet cache invalidated after import.")
    except Exception:  # noqa: BLE001 - cache invalidation is best-effort
        logger.warning("Could not invalidate facet cache.", exc_info=True)

    # Both phases succeeded: finalise the run with the advanced end state
    # (crawl_oparl has already set it to the latest timestamp seen).
    recorder.finish(success=True)
    logger.info("Incremental sync finished successfully.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-command incremental OParl synchronisation (crawl + pgGen import)."
    )
    parser.add_argument("--system-url", default=SYSTEM_URL,
                        help="Base URL of the OParl system (default: %(default)s)")
    parser.add_argument("--output-folder", default=OUTPUT_FOLDER,
                        help="Folder with crawled JSON files (default: %(default)s)")
    parser.add_argument("--last-date", default=None,
                        help="ISO timestamp overriding the tracked baseline")
    args = parser.parse_args()
    raise SystemExit(sync(system_url=args.system_url,
                          output_folder=args.output_folder,
                          last_date=args.last_date))


if __name__ == "__main__":
    main()
