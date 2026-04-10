const mysql = require("mysql2/promise");
const fs = require("fs");
const path = require("path");

async function setup() {
  // Connect WITHOUT specifying a database first
  const conn = await mysql.createConnection({
    host: "127.0.0.1",
    port: 3306,
    user: "root",
    password: "tatakae",
    multipleStatements: true,
  });

  console.log("✓ Connected to MySQL");

  // Create the database
  await conn.query("CREATE DATABASE IF NOT EXISTS art_gallery CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci");
  console.log("✓ Database 'art_gallery' created/verified");

  // Use the database
  await conn.query("USE art_gallery");

  // Read and execute the SQL dump
  const sqlPath = path.join(__dirname, "art_gallery.sql");
  const sql = fs.readFileSync(sqlPath, "utf8");
  await conn.query(sql);
  console.log("✓ SQL dump imported successfully");

  // Run the migration (orders table + is_sold column)
  const migratePath = path.join(__dirname, "migrate.sql");
  const migrateSql = fs.readFileSync(migratePath, "utf8");
  try {
    await conn.query(migrateSql);
    console.log("✓ Migration applied (orders table + is_sold column)");
  } catch (e) {
    console.log("✓ Migration already applied or skipped:", e.message);
  }

  // Verify tables
  const [tables] = await conn.query("SHOW TABLES");
  console.log("\n✓ Tables in art_gallery:");
  tables.forEach((t) => console.log("  -", Object.values(t)[0]));

  // Verify row counts
  const checks = ["users", "artists", "artworks", "categories", "countries", "world_art", "donations", "artist_reviews", "wishlist"];
  console.log("\n✓ Row counts:");
  for (const table of checks) {
    try {
      const [rows] = await conn.query(`SELECT COUNT(*) as c FROM ${table}`);
      console.log(`  - ${table}: ${rows[0].c} rows`);
    } catch (e) {
      console.log(`  - ${table}: ERROR - ${e.message}`);
    }
  }

  await conn.end();
  console.log("\n✅ Database setup complete!");
}

setup().catch((err) => {
  console.error("❌ Setup failed:", err.message);
  process.exit(1);
});
