import mysql from "mysql2/promise";

export const db = mysql.createPool({
   host: "127.0.0.1",
   port: 3306,
   user: "root",
   password: "gunnseth01", // Note: Ensure this matches your newly installed MySQL root password
   database: "art_gallery"
});