import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8090,
    proxy: {
      "/api/opc": {
        target: "http://localhost:5001",
        changeOrigin: true,
        secure: false,
      },
      "/api/plc": {
        target: "http://localhost:5001",
        changeOrigin: true,
        secure: false,
      },
      "/opcHub": {
        target: "http://localhost:5001",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      "/api": {
        target: "http://localhost:6001",
        changeOrigin: true,
        secure: false,
      },
      "/socket.io": {
        target: "http://localhost:6001",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
    },
  },
  preview: {
    port: 8095,
    proxy: {
      "/api/opc": {
        target: "http://localhost:5001",
        changeOrigin: true,
        secure: false,
      },
      "/api/plc": {
        target: "http://localhost:5001",
        changeOrigin: true,
        secure: false,
      },
      "/opcHub": {
        target: "http://localhost:5001",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      "/api": {
        target: "http://localhost:6001",
        changeOrigin: true,
        secure: false,
      },
      "/socket.io": {
        target: "http://localhost:6001",
        changeOrigin: true,
        secure: false,
        ws: true,
      },
    },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
