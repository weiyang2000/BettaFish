import path from "node:path";

const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: path.resolve(process.cwd())
  }
};

export default nextConfig;
