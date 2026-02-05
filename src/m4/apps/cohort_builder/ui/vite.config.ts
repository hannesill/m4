import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { resolve } from "path";

export default defineConfig({
  plugins: [viteSingleFile()],
  root: "src",
  build: {
    outDir: resolve(__dirname, ".."),
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, "src/mcp-app.html"),
    },
  },
});
