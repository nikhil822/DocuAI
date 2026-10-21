
import { useState } from "react";
import { flushSync } from "react-dom";
import "./App.css";

const API_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");


  async function uploadDocument(event) {
    event.preventDefault();
    const form = event.currentTarget;

    if (!selectedFile || uploading) return;

    if (
      selectedFile.type !== "application/pdf" &&
      !selectedFile.name.toLowerCase().endsWith(".pdf")
    ) {
      setUploadError("Please select a PDF file.");
      return;
    }

    setUploading(true);
    setUploadMessage("");
    setUploadError("");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(
        `${API_URL}/documents/ingest`,
        {
          method: "POST",
          body: formData,
        }
      );

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          result.detail || `Upload failed (${response.status})`
        );
      }

      const job = await waitForIngestion(result.job_id);

      setUploadMessage(
        `Successfully processed ${job.document_name}. ` +
        "You can now ask questions about it."
      );

      setSelectedFile(null);
      form.reset();
    } catch (err) {
      setUploadError(err.message || "Document upload failed.");
    } finally {
      setUploading(false);
    }
  }


  async function askQuestion(event) {
    event.preventDefault();

    const trimmedQuestion = question.trim();

    if (!trimmedQuestion || loading) return;

    setQuestion("");
    setError("");
    setLoading(true);

    // Create the user message and an empty assistant message.
    setMessages((previous) => [
      ...previous,
      { role: "user", content: trimmedQuestion },
      { role: "assistant", content: "", sources: [] },
    ]);

    try {
      const response = await fetch(`${API_URL}/ask/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          question: trimmedQuestion,
          top_k: 8,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(
          `Request failed (${response.status}): ${detail}`
        );
      }

      if (!response.body) {
        throw new Error("Streaming response is unavailable.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";
      let streamError = null;
      let receivedDone = false;

      function processEvent(rawEvent) {
        let eventName = "message";
        const dataLines = [];

        for (const line of rawEvent.split(/\r?\n/)) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trimStart());
          }
        }

        if (dataLines.length === 0) return "";

        const payload = JSON.parse(dataLines.join("\n"));

        if (eventName === "token") {
          return payload.text;
        }

        if (eventName === "sources") {
          setMessages((previous) => {
            const updated = [...previous];
            const lastIndex = updated.length - 1;

            updated[lastIndex] = {
              ...updated[lastIndex],
              sources: payload.sources || [],
            };

            return updated;
          });
        }

        if (eventName === "error") {
          streamError = new Error(
            payload.message || "Answer generation failed."
          );
        }

        if (eventName === "done") {
          receivedDone = true;
        }

        return "";
      }

      while (true) {
        const { value, done } = await reader.read();

        buffer += decoder.decode(value || new Uint8Array(), {
          stream: !done,
        });

        // An SSE event ends with a blank line.
        // A network chunk may contain part of an event,
        // several events, or an event boundary.
        const normalized = buffer.replace(/\r\n/g, "\n");
        const events = normalized.split("\n\n");

        buffer = events.pop() || "";
        let chunkText = "";

        for (const rawEvent of events) {
          chunkText += processEvent(rawEvent);
        }

        if (done) {
          if (buffer.trim()) {
            chunkText += processEvent(buffer);
          }
        }

        if (chunkText) {
          flushSync(() => {
            setMessages((previous) => {
              const updated = [...previous];
              const lastIndex = updated.length - 1;
              const lastMessage = updated[lastIndex];

              if (!lastMessage || lastMessage.role !== "assistant") {
                return previous;
              }

              updated[lastIndex] = {
                ...lastMessage,
                content: lastMessage.content + chunkText,
              };

              return updated;
            });
          });

          // Let the browser paint each received text chunk before reading on.
          await new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve))
          );
        }

        if (done) break;
      }

      if (!receivedDone && !streamError) {
        throw new Error(
          "The answer stream ended before completion."
        );
      }

      if (streamError) throw streamError;
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }


  async function waitForIngestion(jobId) {
    while (true) {
      const response = await fetch(
        `${API_URL}/documents/jobs/${jobId}`
      );

      if (!response.ok) {
        throw new Error("Could not retrieve ingestion status.");
      }

      const job = await response.json();

      if (job.status === "completed") {
        return job;
      }

      if (job.status === "failed") {
        throw new Error(
          job.error || "Document ingestion failed."
        );
      }

      // Poll every 1.5 seconds while queued or processing.
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }


  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-icon">D</div>
        <div>
          <h1>Chat With Your Documents</h1>
          <p>Ask questions. Get answers grounded in your PDFs.</p>
        </div>
      </header>

      <section className="chat-panel">

        <form className="upload-panel" onSubmit={uploadDocument}>
          <div className="upload-heading">
            <div>
              <h2>Knowledge base</h2>
              <p>Upload a PDF to make its content searchable.</p>
            </div>
            <span className="upload-icon">PDF</span>
          </div>

          <input
            type="file"
            accept=".pdf,application/pdf"
            disabled={uploading}
            onChange={(event) => {
              setSelectedFile(event.target.files?.[0] || null);
              setUploadMessage("");
              setUploadError("");
            }}
          />

          {selectedFile && (
            <p className="file-name">
              Selected: {selectedFile.name}
            </p>
          )}

          <button
            type="submit"
            disabled={!selectedFile || uploading}
          >
            {uploading ? "Processing document..." : "Upload PDF"}
          </button>

          {uploadMessage && (
            <p className="upload-success" role="status">
              {uploadMessage}
            </p>
          )}

          {uploadError && (
            <p className="error-message" role="alert">
              {uploadError}
            </p>
          )}
        </form>

        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <h2>What would you like to know?</h2>
              <p>
                Ask a question about a document you've already
                ingested into the knowledge base.
              </p>
              <button
                className="suggestion"
                onClick={() =>
                  setQuestion(
                    "How did I reduce peak memory usage during exports?"
                  )
                }
              >
                How did I reduce peak memory usage during exports?
              </button>
            </div>
          )}

          {messages.map((message, index) => (
            <article
              className={`message ${message.role}`}
              key={index}
            >
              <div className="message-label">
                {message.role === "user" ? "You" : "Assistant"}
              </div>

              <div className="message-content">
                {message.content ||
                  (loading && message.role === "assistant"
                    ? "Thinking..."
                    : "")}
                {loading &&
                  message.role === "assistant" &&
                  index === messages.length - 1 &&
                  message.content && (
                    <span className="stream-cursor" />
                  )}
              </div>

              {message.role === "assistant" &&
                message.sources?.length > 0 && (
                  <details className="sources">
                    <summary>
                      Sources ({message.sources.length})
                    </summary>

                    {message.sources.map((source) => (
                      <div
                        className="source-item"
                        key={source.source_id}
                      >
                        <strong>
                          [{source.source_id}]{" "}
                          {source.document_name}
                        </strong>
                        <span>Page {source.page_number}</span>
                        <p>{source.text}</p>
                      </div>
                    ))}
                  </details>
                )}
            </article>
          ))}

          {error && <p className="error-message">{error}</p>}
        </div>

        <form className="question-form" onSubmit={askQuestion}>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a question about your documents..."
            rows={2}
            disabled={loading}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                event.currentTarget.form.requestSubmit();
              }
            }}
          />

          <button
            type="submit"
            disabled={loading || !question.trim()}
          >
            {loading ? "Generating..." : "Ask"}
          </button>
        </form>

        <p className="disclaimer">
          Answers are generated from retrieved document content.
          Verify important information against the original source.
        </p>
      </section>
    </main>
  );
}
