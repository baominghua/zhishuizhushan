import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteStaticCopy } from "vite-plugin-static-copy";

export default defineConfig({
  base: "/v2/",
  publicDir: false,
  define: {
    CESIUM_BASE_URL: JSON.stringify("/v2/cesiumStatic/1.144.0/"),
  },
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        {
          src: "node_modules/cesium/Build/Cesium/Workers",
          dest: "cesiumStatic/1.144.0",
          rename: { stripBase: 4 },
        },
        {
          src: "node_modules/cesium/Build/Cesium/ThirdParty",
          dest: "cesiumStatic/1.144.0",
          rename: { stripBase: 4 },
        },
        {
          src: "node_modules/cesium/Build/Cesium/Assets",
          dest: "cesiumStatic/1.144.0",
          rename: { stripBase: 4 },
        },
        {
          src: "node_modules/cesium/Build/Cesium/Widgets",
          dest: "cesiumStatic/1.144.0",
          rename: { stripBase: 4 },
        },
      ],
    }),
  ],
  build: {
    outDir: "../../dist/web-operations",
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:8024",
    },
  },
});
