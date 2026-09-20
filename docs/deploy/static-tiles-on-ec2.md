# 정적 AOI 타일을 EC2에서 서빙하기 (2026-09-19)

## 왜

`ui/public/tiles`(464MB, 16,509개)와 `ui/public/satellite`(275MB, 15,205개) = **744MB**.

Vercel은 **배포할 때마다 정적 파일을 통째로 새로 저장**하고 옛 배포를 지우기 전까지 계속
들고 있다. 그래서 배포 44번 만에 **32.95GB**까지 올라가 Hobby 한도 10GB를 넘겼다.

코드가 무거운 게 아니라, 같은 744MB가 배포 횟수만큼 복제된 것이다. 플랜 업그레이드 대신
이 두 디렉터리를 Vercel 배포에서 빼고, 이미 돌고 있는 **EC2의 Caddy**가 서빙한다
(VWorld 프록시 때문에 어차피 필요한 서버라 추가 비용 0원).

## 구조

```
브라우저
 ├─ https://<vercel-app>/          → Next.js 앱 (6MB)
 ├─ https://<vercel-app>/aoi/*     → 하천 geojson (5.6MB, 작아서 Vercel에 그대로 둠)
 └─ https://15-164-210-176.sslip.io/
      ├─ /tiles/*      → Caddy file_server  (EC2 디스크에서 직접)
      ├─ /satellite/*  → Caddy file_server
      └─ 그 외          → reverse_proxy localhost:8000 (uvicorn, 기존 그대로)
```

UI 쪽 연결점은 [`ui/src/lib/api.ts`](../../ui/src/lib/api.ts)의 `tileBase` 하나다.
`NEXT_PUBLIC_TILE_BASE`가 없으면 `window.location.origin`으로 떨어지므로
**로컬 `npm run dev`는 아무 설정 없이 그대로 돈다**(`ui/public`에 파일이 있으니까).

## 적용 순서 (순서가 중요하다)

EC2가 타일을 서빙하기 **전에** Vercel에서 먼저 빼면 그사이 지도에 타일이 안 나온다.

### 1단계 — EC2에 Caddy 정적 서빙 추가

EC2 Instance Connect 터미널에서. **한 줄씩** 붙여넣을 것 — 이 브라우저 터미널은 여러 줄을
한 번에 붙이면 bracketed-paste 이스케이프(`^[[200~`)가 첫 명령에 섞여 깨진다.

```bash
df -h /
```
```bash
du -sh ~/Aquaguard/ui/public/tiles ~/Aquaguard/ui/public/satellite
```

744MB가 안 보이면 저장소가 덜 당겨진 것이다:
```bash
cd ~/Aquaguard && git pull
```

Caddy는 `caddy` 사용자로 도는데 Ubuntu의 `/home/ubuntu`는 기본 `0750`이라 통과를 못 한다.
실행 비트만 열어준다(디렉터리 목록 노출 아님, 통과만 허용):
```bash
sudo chmod o+x /home/ubuntu
```

현재 Caddyfile 확인:
```bash
sudo cat /etc/caddy/Caddyfile
```

`15-164-210-176.sslip.io { ... }` 블록 안을 아래로 교체한다
(`sudo nano /etc/caddy/Caddyfile`). **`handle_path`가 `reverse_proxy`보다 위**에 있어야
`/tiles/*`가 uvicorn으로 새지 않는다:

```caddyfile
15-164-210-176.sslip.io {
	# 정적 AOI 타일 — Vercel 배포 용량 때문에 여기서 서빙한다(2026-09-19).
	# handle_path는 매칭된 접두어를 벗겨내므로 root에 접두어를 다시 붙이지 않는다.
	handle_path /tiles/* {
		root * /home/ubuntu/Aquaguard/ui/public/tiles
		header Access-Control-Allow-Origin "*"
		header Cache-Control "public, max-age=31536000, immutable"
		file_server
	}

	handle_path /satellite/* {
		root * /home/ubuntu/Aquaguard/ui/public/satellite
		header Access-Control-Allow-Origin "*"
		header Cache-Control "public, max-age=31536000, immutable"
		file_server
	}

	# 나머지는 기존대로 백엔드로
	handle {
		reverse_proxy localhost:8000
	}
}
```

> **CORS가 필요한 이유**: 타일이 Vercel 앱과 다른 오리진에서 오므로, 이 헤더가 없으면
> MapLibre의 타일 요청이 브라우저에서 차단된다. 공개 지도 타일이라 `*`로 연다.
>
> **`.pbf`는 압축 안 된 원본**이라(2026-09-19 확인: 첫 바이트 `1a a1`, gzip 매직 `1f 8b`가
> 아님) `Content-Encoding` 설정이 필요 없다.

검증 후 적용:
```bash
sudo caddy validate --config /etc/caddy/Caddyfile
```
```bash
sudo systemctl reload caddy
```

### 2단계 — 서빙되는지 확인

세 개 다 `200`이어야 한다. 마지막 줄은 기존 백엔드가 안 깨졌는지 보는 것이다.

```bash
curl -sI https://15-164-210-176.sslip.io/tiles/sancheong-buildings/10/875/403.pbf | head -5
```
```bash
curl -sI https://15-164-210-176.sslip.io/satellite/sancheong/10/875/403.jpg | head -5
```
```bash
curl -s https://15-164-210-176.sslip.io/health
```

`403`이면 `chmod o+x /home/ubuntu`가 빠진 것, `404`면 경로나 `git pull`,
`200`인데 JSON이 오면 `handle_path`가 `reverse_proxy` 아래에 있는 것이다.

### 3단계 — Vercel 환경변수

Vercel → 프로젝트 → Settings → Environment Variables:

| Key | Value |
|---|---|
| `NEXT_PUBLIC_TILE_BASE` | `https://15-164-210-176.sslip.io` |

Production/Preview/Development 전부 체크. `NEXT_PUBLIC_*`는 **빌드 시점에 번들로 구워지므로**
값을 바꾸면 반드시 재배포해야 반영된다(런타임에 안 읽는다).

### 4단계 — 푸시

`.vercelignore`가 들어간 커밋을 푸시하면 자동 재배포된다. 이때부터 배포 크기가
**744MB → 약 6MB**가 된다.

### 5단계 — 옛 배포 삭제 (이미 쌓인 32.95GB 회수)

Vercel → Deployments → 최신 Production 하나와 직전 하나만 남기고 삭제.
4단계를 먼저 끝내야 새로 쌓이지 않는다.

## 되돌리기

Vercel에서 `NEXT_PUBLIC_TILE_BASE`를 지우고 `.vercelignore`의 두 줄을 빼면 원래대로
Vercel이 서빙한다(용량 문제도 같이 돌아온다).

## 주의

- **`ui/public/tiles`·`ui/public/satellite`는 여전히 git에 커밋돼 있다.** EC2가 `git pull`로
  받는 경로라 의도한 것이다. 다만 `.git`이 562MB라 clone이 무겁다 — 히스토리에서 들어내려면
  `git filter-repo`가 필요하고 팀원 전원이 다시 clone해야 하므로 별개 작업으로 둔다.
- 타일을 새로 생성하면(`scripts/build_aoi_*`) 커밋 후 **EC2에서 `git pull`**을 해야 반영된다.
  Vercel 재배포만으로는 안 바뀐다.
