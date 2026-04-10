const mysql = require("mysql2/promise");

async function migrate() {
  const conn = await mysql.createConnection({
    host: "127.0.0.1",
    port: 3306,
    user: "root",
    password: "tatakae",
    database: "art_gallery",
    multipleStatements: true,
  });

  // Add is_sold column if it doesn't exist
  try {
    await conn.query("ALTER TABLE artworks ADD COLUMN is_sold BOOLEAN DEFAULT FALSE");
    console.log("✓ Added is_sold column to artworks");
  } catch (e) {
    if (e.message.includes("Duplicate column")) {
      console.log("✓ is_sold column already exists");
    } else {
      console.log("⚠ is_sold:", e.message);
    }
  }

  // Create orders table
  try {
    await conn.query(`
      CREATE TABLE IF NOT EXISTS orders (
        order_id INT NOT NULL AUTO_INCREMENT,
        artwork_id INT NOT NULL,
        buyer_name VARCHAR(255) NOT NULL,
        shipping_address TEXT NOT NULL,
        ordered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (order_id),
        KEY artwork_id (artwork_id),
        CONSTRAINT orders_ibfk_1 FOREIGN KEY (artwork_id) REFERENCES artworks(artwork_id) ON DELETE CASCADE
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    `);
    console.log("✓ Orders table created/verified");
  } catch (e) {
    console.log("⚠ orders:", e.message);
  }

  // Verify
  const [tables] = await conn.query("SHOW TABLES");
  console.log("\nTables:", tables.map(t => Object.values(t)[0]).join(", "));

  await conn.end();
  console.log("\n✅ Migration complete!");
}

migrate().catch(console.error);
