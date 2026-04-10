// Run this script ONCE to set a bcrypt password hash for existing users
// Usage: node set_admin_password.js
const bcrypt = require("bcryptjs");
const mysql = require("mysql2/promise");

async function setPasswords() {
  const conn = await mysql.createConnection({
    host: "127.0.0.1",
    port: 3306,
    user: "root",
    password: "gunnseth01",
    database: "art_gallery",
  });

  // Set password "admin123" for the admin user (user_id=1)
  const adminHash = await bcrypt.hash("admin123", 10);
  await conn.query("UPDATE users SET password_hash = ? WHERE user_id = ?", [adminHash, 1]);
  console.log("✓ Admin password set to: admin123");

  // Set password "user123" for Gunn Seth (user_id=3)
  const userHash = await bcrypt.hash("user123", 10);
  await conn.query("UPDATE users SET password_hash = ? WHERE user_id = ?", [userHash, 3]);
  console.log("✓ Gunn Seth password set to: user123");

  // Set password "artist123" for Karthik sir (user_id=5)
  const artistHash = await bcrypt.hash("artist123", 10);
  await conn.query("UPDATE users SET password_hash = ? WHERE user_id = ?", [artistHash, 5]);
  console.log("✓ Karthik sir password set to: artist123");

  await conn.end();
  console.log("\n✅ All existing user passwords have been set!");
  console.log("\nCredentials:");
  console.log("  Admin:   test@example.com / admin123");
  console.log("  Viewer:  gunnseth41@gmail.com / user123");
  console.log("  Artist:  ss@gmail.com / artist123");
}

setPasswords().catch(console.error);
