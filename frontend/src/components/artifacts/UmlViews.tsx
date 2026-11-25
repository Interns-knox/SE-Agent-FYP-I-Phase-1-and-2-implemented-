import { DiagramViewer } from "./DiagramViewer";
import type { RenderOptions } from "./renderContent";

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

/** Every diagram of a UML artifact, rendered visually first with source on demand. */
export function UmlDiagramsView({
  content,
  onSaveSource,
  disabled,
}: { content: Obj } & RenderOptions) {
  const diagrams = arr(content.diagrams);
  if (diagrams.length === 0) {
    return <p className="artifact__muted">This artifact contains no diagrams.</p>;
  }
  return (
    <div>
      {diagrams.map((d, i) => (
        <div key={`${d.id}-${i}`}>
          <DiagramViewer
            title={String(d.title ?? "Diagram")}
            diagramId={String(d.id ?? "")}
            source={String(d.plantuml ?? "")}
            disabled={disabled}
            onSaveSource={onSaveSource ? (src) => onSaveSource(i, src) : undefined}
          />
          <p className="artifact__muted">
            Requirements: <Chips items={d.requirement_ids} /> Domain entities:{" "}
            <Chips items={d.domain_entity_ids} /> Components: <Chips items={d.component_ids} />
          </p>
        </div>
      ))}
    </div>
  );
}

/** Domain model: the diagram first, then the structured entities, relationships and rules. */
export function DomainModelView({
  content,
  onSaveSource,
  disabled,
}: { content: Obj } & RenderOptions) {
  const model: Obj = content.model ?? {};
  const entities = arr(model.entities);
  const relationships = arr(model.relationships);
  const rules = arr(model.business_rules);
  return (
    <div>
      <UmlDiagramsView content={content} onSaveSource={onSaveSource} disabled={disabled} />
      <details open>
        <summary>
          <strong>Entities ({entities.length})</strong>
        </summary>
        <div className="table-wrap">
          <table className="artifact-table" data-testid="dm-entities">
            <thead>
              <tr>
                <th>ID</th>
                <th>Entity</th>
                <th>Responsibility</th>
                <th>Attributes</th>
                <th>Requirements</th>
              </tr>
            </thead>
            <tbody>
              {entities.map((e) => (
                <tr key={String(e.id)}>
                  <td>
                    <code>{String(e.id ?? "")}</code>
                  </td>
                  <td>
                    <strong>{String(e.name ?? "")}</strong>
                    <div className="artifact__muted">
                      {String(e.kind ?? "").toLowerCase().replace(/_/g, " ")}
                    </div>
                  </td>
                  <td>
                    {String(e.description ?? "")}
                    <ul className="artifact-table__list">
                      {(Array.isArray(e.responsibilities) ? (e.responsibilities as unknown[]) : []).map(
                        (r, j) => (
                          <li key={j}>{String(r)}</li>
                        ),
                      )}
                    </ul>
                  </td>
                  <td>
                    <ul className="artifact-table__list">
                      {arr(e.attributes).map((a, j) => (
                        <li key={j}>
                          <code>{String(a.name)}</code>
                          {a.type ? ` : ${String(a.type)}` : ""}
                        </li>
                      ))}
                    </ul>
                  </td>
                  <td>
                    <Chips items={e.requirement_ids} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <details open>
        <summary>
          <strong>Relationships ({relationships.length})</strong>
        </summary>
        <div className="table-wrap">
          <table className="artifact-table" data-testid="dm-relationships">
            <thead>
              <tr>
                <th>From</th>
                <th>Relationship</th>
                <th>To</th>
                <th>Cardinality</th>
              </tr>
            </thead>
            <tbody>
              {relationships.map((r) => (
                <tr key={String(r.id)}>
                  <td>{String(r.from)}</td>
                  <td>
                    {String(r.kind ?? "").toLowerCase()}
                    {r.label ? `: ${String(r.label)}` : ""}
                  </td>
                  <td>{String(r.to)}</td>
                  <td>
                    {r.kind === "INHERITANCE"
                      ? "-"
                      : `${String(r.from_cardinality)} to ${String(r.to_cardinality)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <details open>
        <summary>
          <strong>Business rules ({rules.length})</strong>
        </summary>
        {rules.length === 0 ? (
          <p className="artifact__muted">No business rules documented.</p>
        ) : (
          <ul>
            {rules.map((r) => (
              <li key={String(r.id)}>
                <code>{String(r.id)}</code> {String(r.description)}{" "}
                <Chips items={r.entities} /> <Chips items={r.requirement_ids} />
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}
