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
          // 2026-08-29: 원래 max-age=31536000+immutable이었다가, 건물 height_m 버그를
          // 고쳐서 타일을 재생성했는데도 브라우저가 예전 파일을 계속 캐시에서 써서
          // (immutable은 "이 URL의 내용은 절대 안 바뀐다"는 약속이라 재검증 요청 자체를
          // 안 보냄) 디버깅이 한참 꼬였다 — z/x/y 경로가 콘텐츠 버전을 담고 있지 않아
          // 이 약속을 못 지킨다. 1시간으로 낮춰서 데모 세션 안에서는 여전히 빠르게
          // 캐시되지만, 다음에 또 타일을 고치면 최대 1시간 안에 저절로 반영되게 함.
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
    ];
  },
};

export default nextConfig;
