import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 산청·서울 AOI 사전 계산 벡터 타일(ui/public/tiles/**/*.pbf) — 여기서 직접
  // Content-Encoding: gzip을 강제했다가(§build_vector_tiles.mjs 2026-08-28 주석
  // 참조) 실제 폴리곤 밖이라 안 만든 타일을 요청했을 때 Next의 404 응답(gzip
  // 아님)에도 이 헤더가 그대로 붙어 브라우저 디코딩이 깨지는 문제가 있었다.
  // 압축은 Vercel/Next의 표준 자동 압축에 맡기고, 여기서는 MIME 타입과
  // 캐시 정책만 지정한다(둘 다 상태코드와 무관하게 항상 맞는 값).
  async headers() {
    return [
      {
        source: "/tiles/:layer/:z/:x/:y.pbf",
        headers: [
          { key: "Content-Type", value: "application/x-protobuf" },
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
    ];
  },
};

export default nextConfig;
