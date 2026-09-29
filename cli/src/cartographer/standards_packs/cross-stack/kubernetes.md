# Kubernetes

## Workloads

- Never use `:latest` image tags in Kubernetes manifests. Pin to a specific semantic
  version or image digest. Non-deterministic tags make deployments unreproducible and
  hide breaking changes.
- Set both `resources.requests` and `resources.limits` on every container. Missing
  requests cause unpredictable scheduling; missing limits allow a runaway container to
  starve the node. Limits without requests default requests to limits and over-reserve
  capacity.
- Use `RollingUpdate` strategy with `maxUnavailable: 0` and `maxSurge: 1` to prevent
  reducing capacity below desired replica count during updates.
- Set `terminationGracePeriodSeconds` to give the application enough time to finish
  in-flight requests before the container is killed.

## Probes

- Configure all three probe types. `startupProbe` gives slow-starting apps (JVM,
  Python) time to initialize; it runs first, then hands off to liveness and readiness.
  `livenessProbe` detects hung processes and triggers a restart. `readinessProbe`
  removes the pod from the service endpoints when it is temporarily unavailable (e.g.,
  reconnecting to the database) without restarting it.
- Do not use `initialDelaySeconds` on `livenessProbe` as a workaround for slow startup.
  Use a `startupProbe` with `failureThreshold × periodSeconds` covering the maximum
  startup time instead.
- Use separate `/health` (liveness) and `/ready` (readiness) endpoints. The readiness
  endpoint should check downstream dependencies; the liveness endpoint should only
  check that the process is alive.

## Security Context

- Run containers as a non-root user. Set `runAsNonRoot: true` and an explicit
  `runAsUser` UID in the pod and container security context.
- Set `readOnlyRootFilesystem: true`. Mount `emptyDir` volumes for writable paths the
  app needs at runtime (e.g., `/tmp`).
- Set `allowPrivilegeEscalation: false` and `capabilities.drop: [ALL]`. Add back only
  the specific capabilities the app genuinely needs.
- Use dedicated `ServiceAccount` per application with `automountServiceAccountToken:
  false` unless the app calls the Kubernetes API. Never use the `default`
  ServiceAccount.

## RBAC

- Follow least privilege: bind a `Role` (namespace-scoped) rather than a `ClusterRole`
  unless cluster-wide access is genuinely required.
- Grant only the verbs and resources actually needed. Restrict secrets access by
  `resourceNames` to the specific secrets the app requires.
- Audit existing bindings before adding new ones. `ClusterRoleBinding` to
  `cluster-admin` is almost never correct for an application service account.

## Secrets and ConfigMaps

- Kubernetes `Secret` objects are base64-encoded, not encrypted at rest by default. Use
  Sealed Secrets or an External Secrets Operator to manage secrets safely in
  version-controlled manifests.
- Put non-sensitive configuration in `ConfigMap` and inject it via `envFrom` or a file
  mount. Do not put passwords or tokens in `ConfigMap`.

## Autoscaling

- Use `HorizontalPodAutoscaler` for variable-load services. Set `minReplicas: 2+` for
  any production workload to maintain availability during rolling updates.
- HPA requires `resources.requests` to be set on containers — it computes utilization
  as `current / request`.
- Define a `PodDisruptionBudget` for stateful or critical services to prevent too many
  pods going down during node drains or updates.

## Anti-Patterns

- Using `:latest` image tag.
- Running as root.
- No resource requests or limits.
- Storing secrets in `ConfigMap`.
- Binding application service accounts to `cluster-admin`.
- `minAvailable: 0` on a PodDisruptionBudget (defeats its purpose).
- `restartPolicy: Always` on a `Job` (causes an infinite restart loop on failure).

## Reliability Checklist

- All three probe types configured (startup + liveness + readiness).
- `resources.requests` and `resources.limits` set on every container.
- `minReplicas: 2+` in HPA for any production workload.
- `PodDisruptionBudget` defined for stateful or critical services.
- `RollingUpdate` strategy with `maxUnavailable: 0`.
- Non-root user, read-only root filesystem, all capabilities dropped.
- ServiceAccount per app with token disabled unless K8s API access is needed.
- Secrets managed via Sealed Secrets or External Secrets Operator.
