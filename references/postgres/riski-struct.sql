/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19  Distrib 10.11.15-MariaDB, for Linux (x86_64)
--
-- Host: localhost    Database: riski
-- ------------------------------------------------------
-- Server version	10.11.15-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `AgendaItem`
--

DROP TABLE IF EXISTS `AgendaItem`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `AgendaItem` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `end` datetime DEFAULT NULL,
  `name` varchar(256) DEFAULT NULL,
  `number` varchar(256) DEFAULT NULL,
  `order` datetime DEFAULT NULL,
  `public` datetime DEFAULT NULL,
  `result` varchar(256) DEFAULT NULL,
  `start` datetime DEFAULT NULL,
  `consultationSid` bigint(20) DEFAULT NULL,
  `meetingSid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_AgendaItem_oparlId` (`oparlId`),
  KEY `ix_AgendaItem_oparlKey` (`oparlKey`),
  KEY `ix_AgendaItem_id` (`id`),
  KEY `ix_AgendaItem_meetingSid` (`meetingSid`),
  KEY `ix_AgendaItem_consultationSid` (`consultationSid`),
  CONSTRAINT `AgendaItem_ibfk_1` FOREIGN KEY (`meetingSid`) REFERENCES `Meeting` (`sid`),
  CONSTRAINT `AgendaItem_ibfk_2` FOREIGN KEY (`consultationSid`) REFERENCES `Consultation` (`sid`)
) ENGINE=InnoDB AUTO_INCREMENT=18095 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `AgendaItem__auxiliaryFile__File`
--

DROP TABLE IF EXISTS `AgendaItem__auxiliaryFile__File`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `AgendaItem__auxiliaryFile__File` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `AgendaItem__auxiliaryFile__File_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `AgendaItem` (`sid`),
  CONSTRAINT `AgendaItem__auxiliaryFile__File_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `File` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Body`
--

DROP TABLE IF EXISTS `Body`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Body` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `agendaItem` varchar(256) DEFAULT NULL,
  `consultation` varchar(256) DEFAULT NULL,
  `contactEmail` varchar(256) DEFAULT NULL,
  `contactName` varchar(256) DEFAULT NULL,
  `file` varchar(256) DEFAULT NULL,
  `legislativeTermList` varchar(256) DEFAULT NULL,
  `licenseValidSince` datetime DEFAULT NULL,
  `locationList` varchar(256) DEFAULT NULL,
  `meeting` varchar(256) DEFAULT NULL,
  `membership` varchar(256) DEFAULT NULL,
  `name` varchar(256) DEFAULT NULL,
  `oparlSince` datetime DEFAULT NULL,
  `organization` varchar(256) DEFAULT NULL,
  `paper` varchar(256) DEFAULT NULL,
  `person` varchar(256) DEFAULT NULL,
  `shortName` varchar(256) DEFAULT NULL,
  `website` varchar(256) DEFAULT NULL,
  `systemSid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_Body_oparlId` (`oparlId`),
  KEY `ix_Body_oparlKey` (`oparlKey`),
  KEY `ix_Body_systemSid` (`systemSid`),
  KEY `ix_Body_id` (`id`),
  CONSTRAINT `Body_ibfk_1` FOREIGN KEY (`systemSid`) REFERENCES `System` (`sid`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Body__legislativeTerm__LegislativeTerm`
--

DROP TABLE IF EXISTS `Body__legislativeTerm__LegislativeTerm`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Body__legislativeTerm__LegislativeTerm` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Body__legislativeTerm__LegislativeTerm_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Body` (`sid`),
  CONSTRAINT `Body__legislativeTerm__LegislativeTerm_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `LegislativeTerm` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Consultation`
--

DROP TABLE IF EXISTS `Consultation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Consultation` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `authoritative` datetime DEFAULT NULL,
  `role` varchar(256) DEFAULT NULL,
  `agendaItemSid` bigint(20) DEFAULT NULL,
  `meetingSid` bigint(20) DEFAULT NULL,
  `paperSid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_Consultation_oparlId` (`oparlId`),
  KEY `ix_Consultation_agendaItemSid` (`agendaItemSid`),
  KEY `ix_Consultation_oparlKey` (`oparlKey`),
  KEY `ix_Consultation_paperSid` (`paperSid`),
  KEY `ix_Consultation_id` (`id`),
  KEY `ix_Consultation_meetingSid` (`meetingSid`),
  CONSTRAINT `Consultation_ibfk_1` FOREIGN KEY (`meetingSid`) REFERENCES `Meeting` (`sid`),
  CONSTRAINT `Consultation_ibfk_2` FOREIGN KEY (`paperSid`) REFERENCES `Paper` (`sid`),
  CONSTRAINT `Consultation_ibfk_3` FOREIGN KEY (`agendaItemSid`) REFERENCES `AgendaItem` (`sid`)
) ENGINE=InnoDB AUTO_INCREMENT=14488 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Consultation__organization__Organization`
--

DROP TABLE IF EXISTS `Consultation__organization__Organization`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Consultation__organization__Organization` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Consultation__organization__Organization_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Consultation` (`sid`),
  CONSTRAINT `Consultation__organization__Organization_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Organization` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `File`
--

DROP TABLE IF EXISTS `File`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `File` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `accessUrl` varchar(256) DEFAULT NULL,
  `date` datetime DEFAULT NULL,
  `downloadUrl` varchar(256) DEFAULT NULL,
  `fileName` varchar(256) DEFAULT NULL,
  `mimeType` varchar(256) DEFAULT NULL,
  `name` varchar(256) DEFAULT NULL,
  `content` text DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_File_oparlId` (`oparlId`),
  KEY `ix_File_oparlKey` (`oparlKey`),
  KEY `ix_File_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=46370 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `File__meeting__Meeting`
--

DROP TABLE IF EXISTS `File__meeting__Meeting`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `File__meeting__Meeting` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `File__meeting__Meeting_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `File` (`sid`),
  CONSTRAINT `File__meeting__Meeting_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Meeting` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `File__paper__Paper`
--

DROP TABLE IF EXISTS `File__paper__Paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `File__paper__Paper` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `File__paper__Paper_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `File` (`sid`),
  CONSTRAINT `File__paper__Paper_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Paper` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `LegislativeTerm`
--

DROP TABLE IF EXISTS `LegislativeTerm`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `LegislativeTerm` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `name` varchar(256) DEFAULT NULL,
  `startDate` datetime DEFAULT NULL,
  `bodySid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_LegislativeTerm_oparlId` (`oparlId`),
  KEY `ix_LegislativeTerm_id` (`id`),
  KEY `ix_LegislativeTerm_oparlKey` (`oparlKey`),
  KEY `ix_LegislativeTerm_bodySid` (`bodySid`),
  CONSTRAINT `LegislativeTerm_ibfk_1` FOREIGN KEY (`bodySid`) REFERENCES `Body` (`sid`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Location`
--

DROP TABLE IF EXISTS `Location`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Location` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `description` varchar(256) DEFAULT NULL,
  `locality` varchar(256) DEFAULT NULL,
  `postalCode` varchar(256) DEFAULT NULL,
  `room` varchar(256) DEFAULT NULL,
  `streetAddress` varchar(256) DEFAULT NULL,
  `subLocality` varchar(256) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_Location_oparlId` (`oparlId`),
  KEY `ix_Location_id` (`id`),
  KEY `ix_Location_oparlKey` (`oparlKey`)
) ENGINE=InnoDB AUTO_INCREMENT=2719 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Meeting`
--

DROP TABLE IF EXISTS `Meeting`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Meeting` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `end` datetime DEFAULT NULL,
  `name` varchar(256) DEFAULT NULL,
  `start` datetime DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_Meeting_oparlId` (`oparlId`),
  KEY `ix_Meeting_id` (`id`),
  KEY `ix_Meeting_oparlKey` (`oparlKey`)
) ENGINE=InnoDB AUTO_INCREMENT=2604 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Meeting__agendaItem__AgendaItem`
--

DROP TABLE IF EXISTS `Meeting__agendaItem__AgendaItem`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Meeting__agendaItem__AgendaItem` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Meeting__agendaItem__AgendaItem_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Meeting` (`sid`),
  CONSTRAINT `Meeting__agendaItem__AgendaItem_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `AgendaItem` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Meeting__auxiliaryFile__File`
--

DROP TABLE IF EXISTS `Meeting__auxiliaryFile__File`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Meeting__auxiliaryFile__File` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Meeting__auxiliaryFile__File_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Meeting` (`sid`),
  CONSTRAINT `Meeting__auxiliaryFile__File_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `File` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Meeting__organization__Organization`
--

DROP TABLE IF EXISTS `Meeting__organization__Organization`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Meeting__organization__Organization` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Meeting__organization__Organization_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Meeting` (`sid`),
  CONSTRAINT `Meeting__organization__Organization_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Organization` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Membership`
--

DROP TABLE IF EXISTS `Membership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Membership` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `endDate` datetime DEFAULT NULL,
  `role` varchar(256) DEFAULT NULL,
  `startDate` datetime DEFAULT NULL,
  `votingRight` datetime DEFAULT NULL,
  `organizationSid` bigint(20) DEFAULT NULL,
  `personSid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_Membership_oparlId` (`oparlId`),
  KEY `ix_Membership_oparlKey` (`oparlKey`),
  KEY `ix_Membership_personSid` (`personSid`),
  KEY `ix_Membership_id` (`id`),
  KEY `ix_Membership_organizationSid` (`organizationSid`),
  CONSTRAINT `Membership_ibfk_1` FOREIGN KEY (`organizationSid`) REFERENCES `Organization` (`sid`),
  CONSTRAINT `Membership_ibfk_2` FOREIGN KEY (`personSid`) REFERENCES `Person` (`sid`)
) ENGINE=InnoDB AUTO_INCREMENT=3026 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Organization`
--

DROP TABLE IF EXISTS `Organization`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Organization` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `classification` varchar(256) DEFAULT NULL,
  `endDate` datetime DEFAULT NULL,
  `meeting` varchar(256) DEFAULT NULL,
  `name` varchar(256) DEFAULT NULL,
  `shortName` varchar(256) DEFAULT NULL,
  `startDate` datetime DEFAULT NULL,
  `bodySid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_Organization_oparlId` (`oparlId`),
  KEY `ix_Organization_bodySid` (`bodySid`),
  KEY `ix_Organization_id` (`id`),
  KEY `ix_Organization_oparlKey` (`oparlKey`),
  CONSTRAINT `Organization_ibfk_1` FOREIGN KEY (`bodySid`) REFERENCES `Body` (`sid`)
) ENGINE=InnoDB AUTO_INCREMENT=97 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Organization__membership__Membership`
--

DROP TABLE IF EXISTS `Organization__membership__Membership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Organization__membership__Membership` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Organization__membership__Membership_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Organization` (`sid`),
  CONSTRAINT `Organization__membership__Membership_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Membership` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Paper`
--

DROP TABLE IF EXISTS `Paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Paper` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `date` datetime DEFAULT NULL,
  `name` varchar(256) DEFAULT NULL,
  `paperType` varchar(256) DEFAULT NULL,
  `reference` varchar(256) DEFAULT NULL,
  `bodySid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_Paper_oparlId` (`oparlId`),
  KEY `ix_Paper_oparlKey` (`oparlKey`),
  KEY `ix_Paper_id` (`id`),
  KEY `ix_Paper_bodySid` (`bodySid`),
  CONSTRAINT `Paper_ibfk_1` FOREIGN KEY (`bodySid`) REFERENCES `Body` (`sid`)
) ENGINE=InnoDB AUTO_INCREMENT=12977 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Paper__auxiliaryFile__File`
--

DROP TABLE IF EXISTS `Paper__auxiliaryFile__File`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Paper__auxiliaryFile__File` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Paper__auxiliaryFile__File_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Paper` (`sid`),
  CONSTRAINT `Paper__auxiliaryFile__File_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `File` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Paper__consultation__Consultation`
--

DROP TABLE IF EXISTS `Paper__consultation__Consultation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Paper__consultation__Consultation` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Paper__consultation__Consultation_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Paper` (`sid`),
  CONSTRAINT `Paper__consultation__Consultation_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Consultation` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Paper__location__Location`
--

DROP TABLE IF EXISTS `Paper__location__Location`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Paper__location__Location` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Paper__location__Location_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Paper` (`sid`),
  CONSTRAINT `Paper__location__Location_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Location` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Paper__subordinatedPaper__Paper`
--

DROP TABLE IF EXISTS `Paper__subordinatedPaper__Paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Paper__subordinatedPaper__Paper` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Paper__subordinatedPaper__Paper_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Paper` (`sid`),
  CONSTRAINT `Paper__subordinatedPaper__Paper_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Paper` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Paper__superordinatedPaper__Paper`
--

DROP TABLE IF EXISTS `Paper__superordinatedPaper__Paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Paper__superordinatedPaper__Paper` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Paper__superordinatedPaper__Paper_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Paper` (`sid`),
  CONSTRAINT `Paper__superordinatedPaper__Paper_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Paper` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Paper__underDirectionOf__Organization`
--

DROP TABLE IF EXISTS `Paper__underDirectionOf__Organization`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Paper__underDirectionOf__Organization` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Paper__underDirectionOf__Organization_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Paper` (`sid`),
  CONSTRAINT `Paper__underDirectionOf__Organization_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Organization` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Person`
--

DROP TABLE IF EXISTS `Person`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Person` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `affix` varchar(256) DEFAULT NULL,
  `familyName` varchar(256) DEFAULT NULL,
  `formOfAddress` varchar(256) DEFAULT NULL,
  `gender` varchar(256) DEFAULT NULL,
  `givenName` varchar(256) DEFAULT NULL,
  `name` varchar(256) DEFAULT NULL,
  `web` varchar(256) DEFAULT NULL,
  `bodySid` bigint(20) DEFAULT NULL,
  `locationSid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_Person_oparlId` (`oparlId`),
  KEY `ix_Person_bodySid` (`bodySid`),
  KEY `ix_Person_oparlKey` (`oparlKey`),
  KEY `ix_Person_locationSid` (`locationSid`),
  KEY `ix_Person_id` (`id`),
  CONSTRAINT `Person_ibfk_1` FOREIGN KEY (`bodySid`) REFERENCES `Body` (`sid`),
  CONSTRAINT `Person_ibfk_2` FOREIGN KEY (`locationSid`) REFERENCES `Location` (`sid`)
) ENGINE=InnoDB AUTO_INCREMENT=704 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Person__membership__Membership`
--

DROP TABLE IF EXISTS `Person__membership__Membership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `Person__membership__Membership` (
  `srcSid` bigint(20) NOT NULL,
  `tgtSid` bigint(20) NOT NULL,
  PRIMARY KEY (`srcSid`,`tgtSid`),
  KEY `tgtSid` (`tgtSid`),
  CONSTRAINT `Person__membership__Membership_ibfk_1` FOREIGN KEY (`srcSid`) REFERENCES `Person` (`sid`),
  CONSTRAINT `Person__membership__Membership_ibfk_2` FOREIGN KEY (`tgtSid`) REFERENCES `Membership` (`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `System`
--

DROP TABLE IF EXISTS `System`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `System` (
  `sid` bigint(20) NOT NULL AUTO_INCREMENT,
  `id` bigint(20) DEFAULT NULL,
  `oparlKey` varchar(255) NOT NULL,
  `oparlId` varchar(512) NOT NULL,
  `type` varchar(255) NOT NULL,
  `created` datetime DEFAULT NULL,
  `modified` datetime DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`data`)),
  `body` varchar(256) DEFAULT NULL,
  `contactEmail` varchar(256) DEFAULT NULL,
  `contactName` varchar(256) DEFAULT NULL,
  `name` varchar(256) DEFAULT NULL,
  `oparlVersion` varchar(256) DEFAULT NULL,
  `product` varchar(256) DEFAULT NULL,
  `vendor` varchar(256) DEFAULT NULL,
  `website` varchar(256) DEFAULT NULL,
  PRIMARY KEY (`sid`),
  UNIQUE KEY `ix_System_oparlId` (`oparlId`),
  KEY `ix_System_oparlKey` (`oparlKey`),
  KEY `ix_System_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-02-19 12:09:01
