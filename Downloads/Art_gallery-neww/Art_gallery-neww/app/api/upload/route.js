import { writeFile, mkdir } from 'fs/promises';
import path from 'path';

export async function POST(req) {
  try {
    const data = await req.formData();
    const file = data.get('file');
    
    if (!file || typeof file === "string") {
      return Response.json({ error: "No valid file found." }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    
    // Sanitize the filename to prevent spaces or weird characters
    const safeName = file.name.replace(/[^a-zA-Z0-9.]/g, "_");
    const filename = `${Date.now()}_${safeName}`;
    const uploadDir = path.join(process.cwd(), "public", "uploads");

    // Ensure the uploads directory exists
    await mkdir(uploadDir, { recursive: true });
    
    // Write it to disk
    await writeFile(path.join(uploadDir, filename), buffer);

    // Return the relative URL which Next.js will serve statically from /public
    return Response.json({ url: `/uploads/${filename}` });
  } catch (err) {
    console.error("Upload API Error:", err);
    return Response.json({ error: err.message }, { status: 500 });
  }
}
