-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)
--
-- Host: localhost    Database: art_gallery
-- ------------------------------------------------------
-- Server version	8.0.45

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `artist_reviews`
--

DROP TABLE IF EXISTS `artist_reviews`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `artist_reviews` (
  `review_id` int NOT NULL AUTO_INCREMENT,
  `artist_id` int DEFAULT NULL,
  `user_id` int DEFAULT NULL,
  `rating` int DEFAULT NULL,
  `comment` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`review_id`),
  KEY `artist_id` (`artist_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `artist_reviews_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `artists` (`artist_id`),
  CONSTRAINT `artist_reviews_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `artist_reviews`
--

LOCK TABLES `artist_reviews` WRITE;
/*!40000 ALTER TABLE `artist_reviews` DISABLE KEYS */;
INSERT INTO `artist_reviews` VALUES (1,4,1,5,'heya','2026-03-19 19:42:26'),(2,4,1,5,'heyaa','2026-03-19 19:42:57'),(3,4,1,5,'heya','2026-03-19 19:44:19'),(4,4,1,3,'nahhh','2026-03-19 19:46:31'),(5,4,1,3,'','2026-03-19 19:46:35'),(6,4,1,3,'yar please','2026-03-19 19:51:22'),(7,4,1,5,'yaya','2026-03-19 19:59:06'),(8,6,1,5,'LOVE IT','2026-03-19 19:59:30'),(9,6,1,3,'OMGG','2026-03-19 20:09:19'),(10,9,1,1,'I DONT LIKE IT\n!!!!!!!!!!!!','2026-03-19 20:10:52'),(11,4,1,2,'bakwas','2026-03-20 05:13:28'),(12,5,1,5,'WAOOOOOOOO','2026-03-20 05:20:15'),(13,6,3,5,'WOA','2026-03-20 08:27:41');
/*!40000 ALTER TABLE `artist_reviews` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `artists`
--

DROP TABLE IF EXISTS `artists`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `artists` (
  `artist_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int DEFAULT NULL,
  `biography` text,
  `country` varchar(100) DEFAULT NULL,
  `profile_image` varchar(255) DEFAULT NULL,
  `name` varchar(100) NOT NULL,
  `slug` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`artist_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `artists_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `artists`
--

LOCK TABLES `artists` WRITE;
/*!40000 ALTER TABLE `artists` DISABLE KEYS */;
INSERT INTO `artists` VALUES (1,NULL,'Italian Renaissance polymath known for masterpieces like the Mona Lisa and The Last Supper.','Italy','/artists/leonardo.jpg','Leonardo da Vinci','leonardo-da-vinci'),(2,NULL,'Dutch post-impressionist painter famous for works like Starry Night and Sunflowers.','Netherlands','/artists/vangogh.jpg','Vincent van Gogh','vincent-van-gogh'),(3,NULL,'Spanish artist and co-founder of the Cubist movement, one of the most influential artists of the 20th century.','Spain','/artists/picasso.jpg','Pablo Picasso','pablo-picasso'),(4,NULL,'Mexican painter known for powerful self-portraits exploring identity, pain, and culture.','Mexico','/artists/kahlo.jpg','Frida Kahlo','frida-kahlo'),(5,NULL,'French painter and founder of the Impressionist movement, known for Water Lilies.','France','/artists/monet.jpg','Claude Monet','claude-monet'),(6,NULL,'Spanish surrealist artist famous for dreamlike imagery and melting clocks.','Spain','/artists/dali.jpg','Salvador Dalí','salvador-dali'),(8,NULL,'Anonymous street artist known for politically charged graffiti and satirical artwork.','United Kingdom','/artists/banksy.jpg','Banksy','banksy'),(9,NULL,'American pop artist known for works featuring Campbell’s soup cans and celebrity portraits.','USA','/artists/warhol.jpg','Andy Warhol','andy-warhol'),(10,NULL,'Italian Renaissance sculptor and painter known for the Sistine Chapel ceiling and David.','Italy','/artists/michelangelo.jpg','Michelangelo','michelangelo'),(13,5,'WP','italy','/uploads/1773995349204_skd.J.png','Karthik sir','karthik-sir');
/*!40000 ALTER TABLE `artists` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `artworks`
--

DROP TABLE IF EXISTS `artworks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `artworks` (
  `artwork_id` int NOT NULL AUTO_INCREMENT,
  `artist_id` int NOT NULL,
  `title` varchar(150) NOT NULL,
  `description` text,
  `image_url` varchar(255) DEFAULT NULL,
  `price` decimal(10,2) DEFAULT NULL,
  `category_id` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`artwork_id`),
  KEY `artist_id` (`artist_id`),
  KEY `category_id` (`category_id`),
  CONSTRAINT `artworks_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `artists` (`artist_id`),
  CONSTRAINT `artworks_ibfk_2` FOREIGN KEY (`category_id`) REFERENCES `categories` (`category_id`)
) ENGINE=InnoDB AUTO_INCREMENT=48 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `artworks`
--

LOCK TABLES `artworks` WRITE;
/*!40000 ALTER TABLE `artworks` DISABLE KEYS */;
INSERT INTO `artworks` VALUES (19,1,'Mona Lisa','Portrait of Lisa Gherardini','/artworks/monalisa.jpg',1000000.00,1,'2026-03-18 13:52:28'),(20,1,'The Last Supper','Depiction of Jesus and his disciples','/artworks/lastsupper.jpg',1200000.00,1,'2026-03-18 13:52:28'),(21,2,'Starry Night','Famous night sky painting','/artworks/starrynight.jpg',950000.00,2,'2026-03-18 13:52:28'),(22,2,'Sunflowers','Series of sunflower paintings','/artworks/sunflowers.jpg',870000.00,2,'2026-03-18 13:52:28'),(23,3,'Guernica','Anti-war painting','/artworks/guernica.jpg',1100000.00,3,'2026-03-18 13:52:28'),(24,3,'Les Demoiselles d’Avignon','Cubist masterpiece','/artworks/demoiselles.jpg',1050000.00,3,'2026-03-18 13:52:28'),(25,4,'The Two Fridas','Double self-portrait','/artworks/twofridas.jpg',800000.00,4,'2026-03-18 13:52:28'),(26,4,'Self Portrait with Thorn Necklace','Symbolic self portrait','/artworks/thornnecklace.jpg',780000.00,4,'2026-03-18 13:52:28'),(27,5,'Water Lilies','Series of water lily paintings','/artworks/waterlilies.jpg',920000.00,5,'2026-03-18 13:52:28'),(28,5,'Impression Sunrise','Gave name to Impressionism','/artworks/sunrise.jpg',910000.00,5,'2026-03-18 13:52:28'),(29,6,'The Persistence of Memory','Melting clocks painting','/artworks/memory.jpg',990000.00,4,'2026-03-18 13:52:28'),(30,6,'Swans Reflecting Elephants','Optical illusion painting','/artworks/swans.jpg',970000.00,4,'2026-03-18 13:52:28'),(31,8,'Girl with Balloon','Iconic street art','/artworks/balloon.jpg',700000.00,7,'2026-03-18 13:52:28'),(32,8,'Flower Thrower','Protester throwing flowers','/artworks/flowerthrower.jpg',720000.00,7,'2026-03-18 13:52:28'),(33,9,'Campbell Soup Cans','Pop art series','/artworks/soup.jpg',880000.00,8,'2026-03-18 13:52:28'),(34,9,'Marilyn Diptych','Marilyn Monroe portrait','/artworks/marilyn.jpg',890000.00,8,'2026-03-18 13:52:28'),(35,10,'Creation of Adam','Sistine Chapel ceiling','/artworks/adam.jpg',1300000.00,1,'2026-03-18 13:52:28'),(36,10,'David','Renaissance sculpture','/artworks/david.jpg',1250000.00,1,'2026-03-18 13:52:28'),(37,1,'Vitruvian Man','Study of human proportions','/artworks/vitruvian.jpg',980000.00,1,'2026-03-18 13:52:44'),(38,2,'Irises','Painting of blooming irises','/artworks/irises.jpg',860000.00,2,'2026-03-18 13:52:44'),(39,3,'The Weeping Woman','Expression of grief and pain','/artworks/weepingwoman.jpg',1020000.00,3,'2026-03-18 13:52:44'),(40,4,'The Broken Column','Depiction of physical and emotional pain','/artworks/brokencolumn.jpg',790000.00,4,'2026-03-18 13:52:44'),(41,5,'Woman with a Parasol','Outdoor portrait in motion','/artworks/parasol.jpg',905000.00,5,'2026-03-18 13:52:44'),(42,6,'The Elephants','Surreal long-legged elephants','/artworks/elephants.jpg',960000.00,4,'2026-03-18 13:52:44'),(43,8,'There Is Always Hope','Girl with balloon variation','/artworks/hope.jpg',710000.00,7,'2026-03-18 13:52:44'),(44,9,'Eight Elvises','Repeated Elvis Presley portraits','/artworks/elvis.jpg',900000.00,8,'2026-03-18 13:52:44'),(45,10,'The Last Judgment','Fresco in Sistine Chapel','/artworks/judgment.jpg',1280000.00,1,'2026-03-18 13:52:44'),(47,13,'ww','ajDgliaskdg','/uploads/1773995384113_Beautiful_background_with_drapery_for_photo_banks____Maria_Zaitseva.jpg',2000.00,8,'2026-03-20 08:29:44');
/*!40000 ALTER TABLE `artworks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `categories`
--

DROP TABLE IF EXISTS `categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `categories` (
  `category_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `slug` varchar(100) DEFAULT NULL,
  `description` text,
  `image_url_1` varchar(500) DEFAULT NULL,
  `image_url_2` varchar(500) DEFAULT NULL,
  `image_url_3` varchar(500) DEFAULT NULL,
  PRIMARY KEY (`category_id`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `categories`
--

LOCK TABLES `categories` WRITE;
/*!40000 ALTER TABLE `categories` DISABLE KEYS */;
INSERT INTO `categories` VALUES (1,'Painting','painting','Traditional art using paint on surfaces.','/categories/painting1.jpg','/categories/painting2.jpg','/categories/painting3.jpg'),(2,'Sculpture','sculpture','Three-dimensional art made from materials like stone or metal.','/categories/sculpture1.jpg','/categories/sculpture2.jpg','/categories/sculpture3.jpg'),(3,'Digital Art','digital-art','Art created using digital tools and software.','/categories/digital1.jpg','/categories/digital2.jpg','/categories/digital3.jpg'),(4,'Photography','photography','Capturing moments using cameras and visual techniques.','/categories/photography1.jpg','/categories/photography2.jpg','/categories/photography3.jpg'),(5,'Renaissance','renaissance','A classical art movement focusing on realism and humanism.','/categories/renaissance1.jpg','/categories/renaissance2.jpg','/categories/renaissance3.jpg'),(6,'Post-Impressionism','post-impressionism','Art focusing on structure and emotional expression.','/categories/postimp1.jpg','/categories/postimp2.jpg','/categories/postimp3.jpg'),(7,'Cubism','cubism','Art style using geometric shapes and fragmented objects.','/categories/cubism1.jpg','/categories/cubism2.jpg','/categories/cubism3.jpg'),(8,'Surrealism','surrealism','Dream-like visuals and imaginative concepts.','/categories/surrealism1.jpg','/categories/surrealism2.jpg','/categories/surrealism3.jpg'),(9,'Impressionism','impressionism','Focus on light, color, and everyday scenes.','/categories/impressionism1.jpg','/categories/impressionism2.jpg','/categories/impressionism3.jpg'),(10,'Modern Art','modern-art','Art that breaks traditional boundaries and explores new ideas.','/categories/modern1.jpg','/categories/modern2.jpg','/categories/modern3.jpg'),(11,'Street Art','street-art','Urban art found in public spaces like graffiti.','/categories/street1.jpg','/categories/street2.jpg','/categories/street3.jpg'),(12,'Pop Art','pop-art','Art inspired by popular culture and mass media.','/categories/pop1.jpg','/categories/pop2.jpg','/categories/pop3.jpg');
/*!40000 ALTER TABLE `categories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `countries`
--

DROP TABLE IF EXISTS `countries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `countries` (
  `country_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `continent` varchar(50) DEFAULT NULL,
  `description` text,
  PRIMARY KEY (`country_id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `countries`
--

LOCK TABLES `countries` WRITE;
/*!40000 ALTER TABLE `countries` DISABLE KEYS */;
INSERT INTO `countries` VALUES (1,'Japan','Asia',NULL),(2,'Egypt','Africa',NULL),(5,'India','Asia',NULL),(6,'France','Europe',NULL);
/*!40000 ALTER TABLE `countries` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `donations`
--

DROP TABLE IF EXISTS `donations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `donations` (
  `donation_id` int NOT NULL AUTO_INCREMENT,
  `artist_id` int DEFAULT NULL,
  `user_id` int DEFAULT NULL,
  `amount` decimal(10,2) DEFAULT NULL,
  `donated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `payment_status` varchar(20) DEFAULT 'success',
  PRIMARY KEY (`donation_id`),
  KEY `artist_id` (`artist_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `donations_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `artists` (`artist_id`),
  CONSTRAINT `donations_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `donations`
--

LOCK TABLES `donations` WRITE;
/*!40000 ALTER TABLE `donations` DISABLE KEYS */;
INSERT INTO `donations` VALUES (1,5,1,50.00,'2026-03-20 06:01:50','success'),(2,6,1,20.00,'2026-03-20 06:04:00','success'),(3,9,1,50.00,'2026-03-20 06:04:28','success'),(4,2,3,500.00,'2026-03-20 08:17:26','success'),(5,13,3,500.00,'2026-03-20 08:30:30','success'),(6,13,3,500.00,'2026-03-20 08:31:11','success'),(7,13,3,1000.00,'2026-03-20 08:31:15','success');
/*!40000 ALTER TABLE `donations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `user_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) DEFAULT NULL,
  `email` varchar(150) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(50) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `username` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `email` (`email`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'Test Admin','test@example.com','dummy_hash','admin','2026-03-19 15:02:57',NULL),(3,'Gunn Seth','gunnseth41@gmail.com','passwordless_hash_1773990150742','user','2026-03-20 07:02:30',NULL),(5,'Karthik sir','ss@gmail.com','none','artist','2026-03-20 08:29:09',NULL);
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `wishlist`
--

DROP TABLE IF EXISTS `wishlist`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `wishlist` (
  `user_id` int NOT NULL,
  `artwork_id` int NOT NULL,
  PRIMARY KEY (`user_id`,`artwork_id`),
  KEY `artwork_id` (`artwork_id`),
  CONSTRAINT `wishlist_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `wishlist`
--

LOCK TABLES `wishlist` WRITE;
/*!40000 ALTER TABLE `wishlist` DISABLE KEYS */;
INSERT INTO `wishlist` VALUES (1,3),(1,5),(1,10),(3,22),(1,29),(1,35),(3,100011),(3,2000002),(3,3000010);
/*!40000 ALTER TABLE `wishlist` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `world_art`
--

DROP TABLE IF EXISTS `world_art`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `world_art` (
  `art_id` int NOT NULL AUTO_INCREMENT,
  `country_id` int DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `image_url` varchar(255) DEFAULT NULL,
  `era` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`art_id`),
  KEY `country_id` (`country_id`),
  CONSTRAINT `world_art_ibfk_1` FOREIGN KEY (`country_id`) REFERENCES `countries` (`country_id`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `world_art`
--

LOCK TABLES `world_art` WRITE;
/*!40000 ALTER TABLE `world_art` DISABLE KEYS */;
INSERT INTO `world_art` VALUES (1,1,'The Great Wave','/art/japan1.jpg','Edo'),(2,1,'Kinkaku-ji Temple','/art/japan2.jpg','Muromachi'),(3,1,'Samurai Armor','/art/japan3.jpg','Sengoku'),(4,2,'The Sphinx','/art/egypt1.jpg','Old Kingdom'),(5,2,'Tutankhamun Mask','/art/egypt2.jpg','18th Dynasty'),(6,2,'Bust of Nefertiti','/art/egypt3.jpg','Amarna Period'),(10,5,'Dancing Girl of Mohenjo-daro','/art/india1.jpg','Indus Valley Civilization'),(11,5,'Ajanta Cave Paintings','/art/india2.jpg','2nd Century BCE'),(12,5,'Radha Bani Thani','/art/india3.jpg','18th Century (Rajput)'),(13,6,'Liberty Leading the People','/art/france1.jpg','Romanticism (1830)'),(14,6,'The Thinker','/art/france2.jpg','Modern Era (1904)'),(15,6,'Water Lilies','/art/france3.jpg','Impressionism (1920)');
/*!40000 ALTER TABLE `world_art` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-03-20 15:09:27
