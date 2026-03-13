/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  transpilePackages: ["@clauselens/shared"],
  async redirects() {
    return [
      { source: "/", destination: "/vendors", permanent: false },
    ];
  },
};

export default nextConfig;
