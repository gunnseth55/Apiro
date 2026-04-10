-- ============================================
-- Art Gallery Database Migration Script
-- Run this ONCE against your art_gallery database
-- ============================================

-- 1. Add is_sold column to artworks (needed for Buy functionality)
ALTER TABLE artworks ADD COLUMN IF NOT EXISTS is_sold BOOLEAN DEFAULT FALSE;

-- 2. Create orders table to track purchases
CREATE TABLE IF NOT EXISTS orders (
  order_id INT NOT NULL AUTO_INCREMENT,
  artwork_id INT NOT NULL,
  buyer_name VARCHAR(255) NOT NULL,
  shipping_address TEXT NOT NULL,
  ordered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (order_id),
  KEY artwork_id (artwork_id),
  CONSTRAINT orders_ibfk_1 FOREIGN KEY (artwork_id) REFERENCES artworks(artwork_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
