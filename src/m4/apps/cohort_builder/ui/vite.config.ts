import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { resolve } from "path";

const outDir = process.env.M4_COHORT_BUILDER_OUT_DIR
  ? resolve(process.env.M4_COHORT_BUILDER_OUT_DIR)
  : resolve(__dirname, "..");

export default defineConfig({
  plugins: [viteSingleFile()],
  root: "src",
  // Disable publicDir since assets are inlined as base64 for single-file output
  publicDir: false,
  build: {
    outDir,
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, "src/mcp-app.html"),
    },
  },
});
