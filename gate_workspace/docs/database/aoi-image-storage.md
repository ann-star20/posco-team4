# AOI 이미지 로컬 보관 및 Aiven 메타데이터

## 설계와 범위

Jetson은 `/home/jetson/project/smart_factory/result/aoi/<job_id>/<attempt>/`에 original.jpg와 annotated.jpg를 보관한다. DB에는 디렉터리, 파일명, 생성된 절대 경로를 각각 기록한다. IP가 바뀌어도 동일 장치를 식별할 수 있도록 device_id를 사용한다. 경로는 HTTP URL이 아니며 Unity에 직접 노출하지 않는다.

`aoi_image_artifacts`는 이미지 한 파일당 한 행이다. 005 migration으로 `inference_jobs`가 추가되었지만 004의 기존 컬럼·데이터 호환성을 위해 job_id는 애플리케이션에서 대응 관계를 검증한다. source_event_id는 events에 대한 선택적 FK다.

주요 필드: artifact_id, job_id, attempt, image_role(original/annotated), device_id, local_directory, file_name, local_path(자동 생성), sha256, byte_size, width, height, captured_at, local_status, cloud_status, cloud_provider, cloud_object_key, cloud_uploaded_at, cloud_error_code, created_at, updated_at.

JPG 저장 성공·해시 계산 후 행을 등록하므로 최초 local_status는 ready다. 촬영/파일 저장 실패는 이미지 행을 조작해 성공으로 표시하지 않고 기존 이벤트로 보존한다. DB 기록 이전 파일 생성 중 장애는 향후 로컬 manifest/outbox로 복구한다. original/annotated는 별도 artifact이며 같은 job/attempt/역할 또는 같은 장치/경로의 중복을 DB에서 막는다.

클라우드는 지금 비활성(disabled). 추후 영속 업로드 대기열과 함께 pending → uploading → uploaded 또는 failed 상태로 관리한다. 업로드를 검사/Unity 표시의 선행 조건으로 삼지 않는다. uploaded에는 provider/object key/완료 시각이 필수다. 영구 식별자는 object key이며 만료되는 signed URL을 저장 위치로 사용하지 않는다. 재시도·lease는 업로더 구현 시 추가한다.

로컬 조회는 예정 Gateway HTTP 중계 → Jetson 인증 이미지 API이며 아직 미구현이다. DB 경로를 그대로 신뢰해 파일을 열지 않고 허용된 root, symlink, 인증, artifact ID를 검증해야 한다. Unity WS에는 결과/이미지 식별자를 전달하고 불량·보류는 자동 조회, 정상은 요청 시 조회하는 정책이다. 검사 결과는 정상도 모두 DB에 보존한다.

클라우드 업로드 전 로컬 고장 시 사진은 유실될 수 있다. 로컬 상태 missing은 사실 기록을 허용한다. 의도적 삭제(deleted)는 이 초기 정책에서는 cloud_status=uploaded일 때만 허용한다. 행은 삭제하지 않고 경로·해시를 유지한다. 용량 부족 시 미백업 파일을 자동 삭제하지 않는다. 실제 파일 존재·클라우드 업로드 무결성은 DB 제약만으로 보장되지 않으며 adapter가 확인해야 한다.

## 적용 계획 / 검증

- [x] `tests/integration/test_aoi_image_migration.py`: 경로 보존·중복·잘못된 파일/경로·업로드 상태 제약 테스트 작성, 테이블 누락으로 RED 확인.
- [x] `database/migrations/004_create_aoi_image_artifacts.sql`: 기존 001~003 변경 없이 테이블/인덱스 추가, 12 passed로 GREEN 확인.
- [ ] Gateway 전체 pytest 실행. 테스트는 고유 임시 스키마만 생성/정리.
- [x] `.env` DATABASE_URL 대상 Aiven public의 기존 001~003 이력 확인 후 기존 migrate 모듈로 004만 적용. 트랜잭션·advisory lock·lock timeout 사용. 기존 행 삭제/수정 없음.
- [x] 운영 테이블 23개 컬럼·migration checksum 일치·재실행 무변경 확인. 운영 artifact 행은 0개이며 가상 검사 데이터를 삽입하지 않음.

운영 인증정보는 `.env`에서만 읽고 로그/문서에 남기지 않는다. 적용 실패 시 트랜잭션을 롤백하며 운영 테이블 DROP으로 되돌리지 않는다. 향후 수정은 후속 migration을 사용한다.

예정 설정: AOI_RESULT_DIR=/home/jetson/project/smart_factory/result/aoi, AOI_CLOUD_BACKUP_ENABLED=false. 현재 앱이 이 키를 읽어 저장/업로드하지는 않는다.

## 직접 확인 SQL

```sql
SELECT version, applied_at FROM schema_migrations
WHERE version = '004_create_aoi_image_artifacts.sql';

SELECT artifact_id, job_id, image_role, device_id,
       local_directory, file_name, local_path,
       sha256, byte_size, local_status, cloud_status
FROM aoi_image_artifacts ORDER BY created_at DESC LIMIT 20;
```

테이블이 비어 있어도 DDL 적용 실패는 아니다. 실제 AOI writer가 아직 연결되지 않았으므로 운영 사진 행을 자동 생성하지 않는다. 임시 스키마 테스트의 가상 행은 운영 테이블에 남기지 않는다.
