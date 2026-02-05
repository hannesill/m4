import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { resolve } from "path";

export default defineConfig({
  plugins: [viteSingleFile()],
  root: "src",
  // Disable publicDir since assets are inlined as base64 for single-file output
  publicDir: false,
  build: {
    outDir: resolve(__dirname, ".."),
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, "src/mcp-app.html"),
    },
  },
});
