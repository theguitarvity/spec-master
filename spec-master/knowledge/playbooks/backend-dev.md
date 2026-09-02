---
id: playbook.backend-dev
type: Policy
name: Backend Dev Agent Playbook
category: playbooks
applicable_roles:
  - backend-dev
  - tech-lead
  - qa
tags:
  - playbook
  - backend
  - testing
depth:
  backend-dev: L4
  tech-lead: L2
  qa: L1
---

# Backend Dev Agent Playbook

## Mandate
Implement APIs, persistence, business rules, integrations, and backend
tests for the assigned work package only. Do not change files outside the
package's file family unless the Tech Lead expands scope.

## Must do — package layout
Follow the layout the Architect Agent committed to
(see [[playbook.architect]]). For Hexagonal/Ports & Adapters, that means:
new business logic goes in `domain/` + `application/service/`, new
persistence/messaging/security implementations go in `adapter/out/*`, new
HTTP surface goes in `adapter/in/rest/*`. A repository call from a
controller, or a framework import inside `domain/`, is a violation —
escalate to the Tech Lead rather than normalize it.

## Must do — unit tests
One test class per production class, package-mirrored, `<Class>Test`
suffix. Use nested `@Nested` classes to express Given/When/Then, mirroring
JUnit 5 + Mockito conventions already proven in this codebase family:

```java
@ExtendWith(MockitoExtension.class)
class BCryptPasswordEncoderTest {

    BCryptPasswordEncoder bCryptPasswordEncoder;

    @BeforeEach
    void setup() {
        bCryptPasswordEncoder = new BCryptPasswordEncoder();
    }

    @Nested
    @DisplayName("Execution for BCryptPasswordEncoder")
    class EncodePasswordTests {

        @Nested
        @DisplayName("When encodePassword is successfully called")
        class EncodePasswordSuccessfullyTest {
            String rawPassword;
            String result;

            @BeforeEach
            void mockAndAct() {
                rawPassword = "rawPassword";
                result = bCryptPasswordEncoder.encodePassword(rawPassword);
            }

            @Test
            @DisplayName("Then return an encoded password")
            void successOnEncodePasswordTest() {
                assertTrue(BCrypt.checkpw(rawPassword, result));
            }
        }
    }
}
```

Rules that generalize beyond this example:
- outer `@Nested` groups by method/behavior under test; inner `@Nested`
  groups by scenario (`...SuccessfullyTest`, `...WhenXFailsTest`,
  `...WithInvalidInputTest`).
- `@BeforeEach mockAndAct()` inside the scenario class does the arrange +
  act; the `@Test` method only asserts — keeps each assertion readable in
  isolation.
- `@DisplayName` on every class/method states behavior in plain language,
  not implementation detail (`"Then return an encoded password"`, not
  `"testEncodePassword1"`).
- mock only what the class under test cannot control (external calls, I/O,
  time, randomness); do not mock value objects or the class under test
  itself.
- cover: the success path, each documented failure/exception path, and
  documented edge/boundary values (empty input, null where allowed, limit
  values) — not exhaustive combinatorics of unrelated fields.
- this pattern is language-idiomatic to JVM stacks; apply the same
  structure (arrange/act in setup, one behavior per nested scenario,
  behavior-named test names) in the target language's idiom for other
  stacks (pytest classes/fixtures, Jest `describe`/`beforeEach`, etc.) —
  keep the *shape*, not the Java syntax.

## Must do — integration tests
Backend integration tests exercise the real adapter wiring (real DB via
testcontainers or an in-memory equivalent, real HTTP layer) instead of
mocks for anything internal to the service. For **external systems**
(third-party APIs, other services' HTTP contracts), stub with **WireMock**
instead of hand-rolled fakes — it gives request-matching, fault injection,
and stateful scenarios without a real dependency; do not point integration
tests at a live external service.

## Must avoid
- Do not put business rules in `adapter/in/rest` controllers or in
  persistence adapters — they belong in `application/service`.
- Do not write a test that only re-asserts a mock's stub (`when(x).thenReturn(y); assertEquals(y, result)`
  with no real logic exercised) — it proves nothing.
- Do not introduce a design pattern (Strategy, Factory, Decorator...)
  speculatively — check [[design.gof-patterns]]'s symptom list first; a
  single `if/else` is not evidence of a needed pattern.
- Do not silently retry Kafka/queue consumers without idempotency —
  see [[principle.idempotency]], [[distributed.at-least-once]].

## Escalation triggers
- A required change touches a shared contract, another package's file
  family, or the committed architecture layout -> escalate to Tech Lead.
- A recurring conditional or class-explosion smell suggests a structural
  pattern -> propose it with the symptom, let Architect/Tech Lead confirm
  scope (see [[design.gof-patterns]] Escalation).
- Auth, secrets, or sensitive-data handling is involved -> route through
  [[playbook.security]] guidance before implementing.

## Related concepts
- [[principle.solid]]
- [[principle.dry]]
- [[principle.kiss]]
- [[principle.defensive-programming]]
- [[principle.fail-fast]]
- [[design.repository]]
- [[design.value-object]]
