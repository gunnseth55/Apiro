import { db } from "@/lib/db";

export async function POST(req) {
    try {
        const { artwork_id, buyer_name, shipping_address } = await req.json();

        if (!artwork_id) {
            return Response.json({ error: "Artwork ID is required" }, { status: 400 });
        }
        if (!buyer_name || !buyer_name.trim()) {
            return Response.json({ error: "Buyer name is required" }, { status: 400 });
        }
        if (!shipping_address || !shipping_address.trim()) {
            return Response.json({ error: "Shipping address is required" }, { status: 400 });
        }

        // Check if artwork exists
        const [artworkRows] = await db.query("SELECT * FROM artworks WHERE artwork_id = ?", [artwork_id]);
        if (artworkRows.length === 0) {
            return Response.json({ error: "Artwork not found" }, { status: 404 });
        }

        // Check if is_sold column exists and artwork is already sold
        const artwork = artworkRows[0];
        if (artwork.is_sold !== undefined && artwork.is_sold) {
            return Response.json({ error: "This artwork has already been sold" }, { status: 400 });
        }

        // Mark artwork as sold (add is_sold column if it doesn't exist)
        try {
            await db.query("UPDATE artworks SET is_sold = true WHERE artwork_id = ?", [artwork_id]);
        } catch (colErr) {
            // If is_sold column doesn't exist, add it first
            if (colErr.message.includes("Unknown column")) {
                await db.query("ALTER TABLE artworks ADD COLUMN is_sold BOOLEAN DEFAULT FALSE");
                await db.query("UPDATE artworks SET is_sold = true WHERE artwork_id = ?", [artwork_id]);
            } else {
                throw colErr;
            }
        }

        // Record the order (create orders table if it doesn't exist)
        try {
            await db.query(
                "INSERT INTO orders (artwork_id, buyer_name, shipping_address) VALUES (?, ?, ?)",
                [artwork_id, buyer_name.trim(), shipping_address.trim()]
            );
        } catch (orderErr) {
            if (orderErr.message.includes("doesn't exist")) {
                // Create orders table on the fly
                await db.query(`
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
                await db.query(
                    "INSERT INTO orders (artwork_id, buyer_name, shipping_address) VALUES (?, ?, ?)",
                    [artwork_id, buyer_name.trim(), shipping_address.trim()]
                );
            } else {
                throw orderErr;
            }
        }

        return Response.json({ message: "Purchase completed successfully! Masterpiece secured." });

    } catch (err) {
        console.error("Buy Error:", err);
        return Response.json({ error: err.message }, { status: 500 });
    }
}
