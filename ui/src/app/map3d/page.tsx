import MapExplorer from "@/components/MapExplorer";

// 지도 자체는 이제 "/"(홈)의 배경이지만, 이 경로도 예전 북마크·직접 링크 호환을 위해
// 남겨둔다 — 로고/메뉴/글라스 패널 오버레이 없이 지도만 단독으로 보고 싶을 때도 유용.
export default function Map3DPage() {
  return <MapExplorer />;
}
