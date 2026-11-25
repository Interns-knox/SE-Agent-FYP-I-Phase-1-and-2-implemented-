/* Read-only, type-specific renderers for artifact content. */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Obj = Record<string, any>;

function arr(value: unknown): Obj[] {
  return Array.isArray(value) ? (value as Obj[]) : [];
}

function Chips({ items }: { items: unknown }) {
  const list = Array.isArray(items) ? (items as unknown[]) : [];
  if (list.length === 0) {
    return <span className="artifact__muted">none</span>;
  }
  return (
    <>
      {list.map((x) => (
        <span key={String(x)} className="chip">
          {String(x)}
        </span>
      ))}
    </>
  );
}

function Fallback({ children }: { children?: unknown }) {
  return children ? <>{String(children)}</> : <span className="artifact__muted">-</span>;
}

export function RequirementsView({ content }: { content: Obj }) {
  const reqs = arr(content.requirements);
  const fr = reqs.filter((r) => r.type !== "NON_FUNCTIONAL");
  const nfr = reqs.filter((r) => r.type === "NON_FUNCTIONAL");
  return (
    <div>
      <h4>Functional requirements ({fr.length})</h4>
      <div className="table-wrap">
        <table className="artifact-table" data-testid="fr-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Requirement</th>
              <th>Actor</th>
              <th>Preconditions</th>
              <th>Expected behavior</th>
              <th>Acceptance criteria</th>
              <th>Priority</th>
              <th>Source features</th>
            </tr>
          </thead>
          <tbody>
            {fr.map((r, i) => (
              <tr key={`${r.id}-${i}`}>
                <td>
                  <code>{String(r.id ?? "")}</code>
                </td>
                <td>
                  <strong>{String(r.title ?? "")}</strong>
                  <div>{String(r.description ?? "")}</div>
                </td>
                <td>
                  <Fallback>{r.actor}</Fallback>
                </td>
                <td>
                  <ul className="artifact-table__list">
                    {(Array.isArray(r.preconditions) ? (r.preconditions as unknown[]) : []).map(
                      (p, j) => (
                        <li key={j}>{String(p)}</li>
                      ),
                    )}
                  </ul>
                </td>
                <td>
                  <Fallback>{r.expected_behavior}</Fallback>
                </td>
                <td>
                  <ul className="artifact-table__list">
                    {(Array.isArray(r.acceptance_criteria)
                      ? (r.acceptance_criteria as unknown[])
                      : []
                    ).map((a, j) => (
                      <li key={j}>{String(a)}</li>
                    ))}
                  </ul>
                </td>
                <td>{String(r.priority ?? "")}</td>
                <td>
                  <Chips items={r.source_feature_ids} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Non-functional requirements ({nfr.length})</h4>
      <div className="table-wrap">
        <table className="artifact-table" data-testid="nfr-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Category</th>
              <th>Requirement</th>
              <th>Measurable criterion</th>
              <th>Priority</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {nfr.map((r, i) => (
              <tr key={`${r.id}-${i}`}>
                <td>
                  <code>{String(r.id ?? "")}</code>
                </td>
                <td>{String(r.category ?? "").replace(/_/g, " ")}</td>
                <td>
                  {r.title ? <strong>{String(r.title)}</strong> : null}
                  <div>{String(r.description ?? "")}</div>
                </td>
                <td>
                  {r.needs_clarification ? (
                    <span className="chip chip--warn">needs clarification</span>
                  ) : null}{" "}
                  <Fallback>
                    {r.measurable_criterion ??
                      (Array.isArray(r.acceptance_criteria)
                        ? (r.acceptance_criteria as unknown[]).join("; ")
                        : "")}
                  </Fallback>
                  {r.clarification_note ? (
                    <div className="artifact__muted">{String(r.clarification_note)}</div>
                  ) : null}
                </td>
                <td>{String(r.priority ?? "")}</td>
                <td>
                  <Chips items={r.source_feature_ids} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SrsView({ content }: { content: Obj }) {
  return (
    <div className="srs">
      {arr(content.sections).map((s, i) => (
        <section key={`${s.id}-${i}`} className="srs__section">
          <h4>
            {i + 1}. {String(s.title ?? s.id ?? "")}
          </h4>
          <p className="srs__body">{String(s.body ?? "")}</p>
        </section>
      ))}
    </div>
  );
}

export function ArchitectureView({ content }: { content: Obj }) {
  return (
    <div>
      <p>
        <strong>Style:</strong> {String(content.style ?? "not stated")}
      </p>
      <div className="table-wrap">
        <table className="artifact-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Component</th>
              <th>Responsibility</th>
              <th>Depends on</th>
              <th>Requirements</th>
            </tr>
          </thead>
          <tbody>
            {arr(content.components).map((c, i) => (
              <tr key={`${c.id}-${i}`}>
                <td>
                  <code>{String(c.id ?? "")}</code>
                </td>
                <td>
                  <strong>{String(c.name ?? "")}</strong>
                  <div className="artifact__muted">
                    {String(c.type ?? "")}
                    {c.technology ? ` / ${String(c.technology)}` : ""}
                  </div>
                </td>
                <td>{String(c.responsibility ?? "")}</td>
                <td>
                  <Chips items={c.depends_on} />
                </td>
                <td>
                  <Chips items={c.requirement_ids} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
