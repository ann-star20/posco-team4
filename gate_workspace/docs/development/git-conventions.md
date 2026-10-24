# Git 커밋 컨벤션

이 문서는 프로젝트에서 사용하는 브랜치 이름과 커밋 메시지 작성 규칙을 정의한다.

## 1. 기본 원칙

- `main` 브랜치에는 직접 커밋하지 않는다.
- 작업 목적에 맞는 별도 브랜치를 생성한다.
- 하나의 커밋에는 하나의 논리적 변경만 포함한다.
- 커밋 메시지만 읽어도 변경 목적을 알 수 있게 작성한다.
- 기능 구현과 관계없는 파일 변경은 같은 커밋에 섞지 않는다.

## 2. 커밋 메시지 형식

```text
<type>(<scope>): <subject>
```

- `type`: 변경의 종류
- `scope`: 변경 대상 또는 모듈이며 필요하지 않으면 생략 가능
- `subject`: 변경 내용을 명령형으로 간결하게 작성

예시:

```text
feat(gateway): add idempotent event ingestion API
fix(outbox): preserve events after request timeout
docs: document ROS 2 event pipeline
test(unity): cover missed event replay
```

## 3. 커밋 타입

- **`feat`**: 새로운 기능을 추가할 때
- **`fix`**: 버그를 수정할 때
- **`docs`**: 문서(README 등)를 수정하거나 추가할 때
- **`style`**: 코드 포맷팅, 세미콜론 누락, 오타 등 비즈니스 로직에 변경이 없는 스타일 수정
- **`refactor`**: 기능 추가나 버그 수정 없이 기존 코드 구조를 개선할 때
- **`test`**: 테스트 코드를 추가하거나 기존 테스트를 수정할 때
- **`chore`**: 개발 도구 설정이나 기타 유지보수 작업을 할 때
- **`perf`**: 성능을 향상시키는 코드 변경을 할 때
- **`build`**: 빌드 시스템이나 외부 의존성에 영향을 주는 변경을 할 때
- **`ci`**: CI 설정 및 스크립트를 변경할 때

## 4. 브랜치 이름 형식

브랜치 이름에도 커밋 타입과 같은 접두사를 사용한다.

```text
<type>/<short-description>
```

예시:

```text
feat/event-ingestion-api
fix/outbox-retry
docs/event-pipeline-design
test/websocket-recovery
refactor/event-repository
chore/local-development
```

브랜치 이름은 영문 소문자와 숫자를 사용하고, 단어는 하이픈(`-`)으로 구분한다.

## 5. 제목 작성 규칙

- 제목 끝에 마침표를 붙이지 않는다.
- 제목은 가능한 한 72자 이내로 작성한다.
- `update`, `change`, `modify`처럼 대상과 목적이 불분명한 표현만 사용하지 않는다.
- 변경 결과를 구체적으로 설명한다.

좋은 예:

```text
feat(bridge): persist ROS 2 events before HTTP delivery
fix(gateway): reject conflicting duplicate event IDs
```

피해야 할 예:

```text
update files
fix bug
changes
```

## 6. 본문과 꼬리말

변경 이유나 주의할 점이 제목만으로 충분하지 않을 때 본문을 추가한다.

```text
fix(outbox): retain event after gateway timeout

The gateway may commit an event even when its HTTP response is lost.
Keep the original event ID and retry until a committed receipt is received.
```

관련 이슈가 있으면 꼬리말에 기록한다.

```text
Closes #12
Refs #8
```

호환성을 깨는 변경은 `!`와 `BREAKING CHANGE`로 표시한다.

```text
feat(api)!: require schema version in event requests

BREAKING CHANGE: Event requests without schema_version are rejected.
```

## 7. 커밋 전 확인

- 변경 목적에 맞는 타입을 사용했는가?
- 테스트가 필요한 변경에 테스트가 포함됐는가?
- 포맷팅이나 관계없는 변경이 섞이지 않았는가?
- 비밀번호, 토큰, 데이터베이스 접속 정보가 포함되지 않았는가?
- 커밋 메시지가 실제 변경 내용을 정확히 설명하는가?
