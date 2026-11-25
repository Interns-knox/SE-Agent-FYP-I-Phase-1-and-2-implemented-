import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, ErrorMessage } from "../components/common";
import { createProject } from "../api/projects";
import { getErrorMessage } from "../api/client";
import "./pages.css";

const NAME_MAX_LENGTH = 255;

export function CreateProjectPage() {
  const navigate = useNavigate();

  const [name, setName] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [submitted, setSubmitted] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const nameError =
    name.trim().length === 0 ? "Project name is required." : null;
  const descriptionError =
    description.trim().length === 0 ? "Description is required." : null;

  const showNameError = submitted && nameError !== null;
  const showDescriptionError = submitted && descriptionError !== null;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    setSubmitError(null);

    if (nameError !== null || descriptionError !== null) {
      return;
    }

    setSubmitting(true);
    try {
      const created = await createProject({
        name: name.trim(),
        description: description.trim(),
      });
      navigate(`/projects/${created.id}`);
    } catch (e) {
      setSubmitError(getErrorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <Link to="/" className="page__back">
        ← Back to dashboard
      </Link>

      <header className="page__header">
        <div>
          <h1 className="page__title">New Project</h1>
          <p className="page__subtitle">
            Describe your project so the AI can extract candidate features.
          </p>
        </div>
      </header>

      <form className="form" onSubmit={handleSubmit} noValidate>
        <div className="form__field">
          <label className="form__label" htmlFor="project-name">
            Name
          </label>
          <input
            id="project-name"
            className={`form__input${
              showNameError ? " form__input--invalid" : ""
            }`}
            type="text"
            value={name}
            maxLength={NAME_MAX_LENGTH}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={showNameError || undefined}
            aria-describedby={showNameError ? "project-name-error" : undefined}
            disabled={submitting}
          />
          <span className="form__hint">
            {name.length}/{NAME_MAX_LENGTH}
          </span>
          {showNameError ? (
            <span id="project-name-error" className="form__error" role="alert">
              {nameError}
            </span>
          ) : null}
        </div>

        <div className="form__field">
          <label className="form__label" htmlFor="project-description">
            Description
          </label>
          <textarea
            id="project-description"
            className={`form__textarea${
              showDescriptionError ? " form__textarea--invalid" : ""
            }`}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            aria-invalid={showDescriptionError || undefined}
            aria-describedby={
              showDescriptionError ? "project-description-error" : undefined
            }
            disabled={submitting}
          />
          {showDescriptionError ? (
            <span
              id="project-description-error"
              className="form__error"
              role="alert"
            >
              {descriptionError}
            </span>
          ) : null}
        </div>

        {submitError ? <ErrorMessage message={submitError} /> : null}

        <div className="form__actions">
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? "Creating..." : "Create Project"}
          </Button>
          <Link to="/" className="page__back">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
