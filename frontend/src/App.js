import React, { useState, useCallback, useRef } from 'react';
import {
  FileText, Figma, Sparkles, Download, Copy, CheckCircle,
  AlertCircle, Loader2, ChevronDown, ChevronRight, Filter,
  BarChart3, Shield, Bug, ArrowRight, Github,
  UploadCloud, X, FileIcon, FilePlus
} from 'lucide-react';
import './App.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

// ── Priority badge ────────────────────────────────────────────────────────────
function PriorityBadge({ p }) {
  const map = { P0: 'badge-p0', P1: 'badge-p1', P2: 'badge-p2' };
  return <span className={`badge ${map[p] || 'badge-p2'}`}>{p}</span>;
}

// ── Type badge ────────────────────────────────────────────────────────────────
function TypeBadge({ type }) {
  const map = {
    happy_path: { label: 'Happy path', cls: 'badge-happy' },
    negative: { label: 'Negative', cls: 'badge-negative' },
    edge_case: { label: 'Edge case', cls: 'badge-edge' },
    accessibility: { label: 'A11y', cls: 'badge-a11y' },
    performance: { label: 'Perf', cls: 'badge-perf' },
  };
  const { label, cls } = map[type] || { label: type, cls: 'badge-edge' };
  return <span className={`badge ${cls}`}>{label}</span>;
}

// ── Single test case card ─────────────────────────────────────────────────────
function TestCard({ tc }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`test-card ${open ? 'open' : ''}`}>
      <button className="test-card-header" onClick={() => setOpen(!open)}>
        <span className="tc-id">{tc.id}</span>
        <span className="tc-title">{tc.title}</span>
        <div className="tc-badges">
          <PriorityBadge p={tc.priority} />
          <TypeBadge type={tc.type} />
        </div>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <div className="test-card-body">
          {tc.component && (
            <div className="tc-row">
              <span className="tc-label">Component</span>
              <span className="tc-value mono">{tc.component}</span>
            </div>
          )}
          {tc.preconditions?.length > 0 && (
            <div className="tc-row">
              <span className="tc-label">Preconditions</span>
              <ul className="tc-list">
                {tc.preconditions.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}
          <div className="tc-row">
            <span className="tc-label">Steps</span>
            <ol className="tc-list ordered">
              {tc.steps?.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </div>
          <div className="tc-row">
            <span className="tc-label">Expected result</span>
            <span className="tc-expected">{tc.expected_result}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Screen section ────────────────────────────────────────────────────────────
function ScreenSection({ screen, filter }) {
  const cases = screen.test_cases?.filter(tc =>
    !filter || filter === 'all' || tc.priority === filter || tc.type === filter
  ) || [];
  if (cases.length === 0) return null;
  return (
    <div className="screen-section">
      <h3 className="screen-name">{screen.screen_name}</h3>
      <div className="tc-count">{cases.length} test cases</div>
      {cases.map(tc => <TestCard key={tc.id} tc={tc} />)}
    </div>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────
function StatsBar({ summary }) {
  if (!summary) return null;
  return (
    <div className="stats-bar">
      <div className="stat"><span className="stat-num">{summary.total}</span><span className="stat-label">Total</span></div>
      <div className="stat-divider" />
      <div className="stat"><span className="stat-num p0">{summary.p0}</span><span className="stat-label">P0</span></div>
      <div className="stat"><span className="stat-num p1">{summary.p1}</span><span className="stat-label">P1</span></div>
      <div className="stat"><span className="stat-num p2">{summary.p2}</span><span className="stat-label">P2</span></div>
      <div className="stat-divider" />
      <div className="stat"><span className="stat-num">{summary.happy_path}</span><span className="stat-label">Happy</span></div>
      <div className="stat"><span className="stat-num">{summary.negative}</span><span className="stat-label">Negative</span></div>
      <div className="stat"><span className="stat-num">{summary.edge_case}</span><span className="stat-label">Edge</span></div>
      <div className="stat"><span className="stat-num">{summary.accessibility}</span><span className="stat-label">A11y</span></div>
    </div>
  );
}

// ── Export helpers ────────────────────────────────────────────────────────────
function toCSV(data) {
  const rows = [['ID', 'Screen', 'Title', 'Type', 'Priority', 'Component', 'Preconditions', 'Steps', 'Expected Result']];
  data.screens?.forEach(s =>
    s.test_cases?.forEach(tc =>
      rows.push([
        tc.id, s.screen_name, tc.title, tc.type, tc.priority, tc.component || '',
        tc.preconditions?.join(' | ') || '',
        tc.steps?.join(' | ') || '',
        tc.expected_result,
      ])
    )
  );
  return rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
}

function downloadFile(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ── File type helpers ─────────────────────────────────────────────────────────
const ACCEPTED = { 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx', 'application/pdf': 'pdf', 'text/plain': 'txt', 'text/markdown': 'md' };
const ACCEPTED_EXT = ['.docx', '.pdf', '.txt', '.md'];

function fileExt(f) {
  return f.name.split('.').pop().toLowerCase();
}
function fileIcon(f) {
  const ext = fileExt(f);
  if (ext === 'pdf') return '📄';
  if (ext === 'docx') return '📝';
  return '📃';
}
function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Drop zone component ───────────────────────────────────────────────────────
function DropZone({ file, onFile, onClear }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef();

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  }, [onFile]);

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const handleDragLeave = () => setDragging(false);
  const handleInputChange = (e) => { if (e.target.files?.[0]) onFile(e.target.files[0]); };

  if (file) {
    return (
      <div className="file-chosen">
        <span className="file-icon-lg">{fileIcon(file)}</span>
        <div className="file-info">
          <span className="file-name">{file.name}</span>
          <span className="file-size">{humanSize(file.size)} · .{fileExt(file)}</span>
        </div>
        <button className="file-clear" onClick={onClear} title="Remove file"><X size={14} /></button>
      </div>
    );
  }

  return (
    <div
      className={`drop-zone ${dragging ? 'dragging' : ''}`}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXT.join(',')}
        style={{ display: 'none' }}
        onChange={handleInputChange}
      />
      <UploadCloud size={28} className="drop-icon" />
      <p className="drop-title">Drop your PRD here</p>
      <p className="drop-sub">or <span className="drop-link">browse files</span></p>
      <div className="drop-types">
        <span className="type-pill">.docx</span>
        <span className="type-pill">.pdf</span>
        <span className="type-pill">.txt</span>
        <span className="type-pill">.md</span>
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState('prd');
  // PRD sub-mode: 'file' | 'paste'
  const [prdMode, setPrdMode] = useState('file');
  const [prdFile, setPrdFile] = useState(null);
  const [prdText, setPrdText] = useState('');
  const [figmaUrl, setFigmaUrl] = useState('');
  const [figmaToken, setFigmaToken] = useState('');
  const [projectName, setProjectName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [filter, setFilter] = useState('all');
  const [copied, setCopied] = useState(false);

  const generate = useCallback(async () => {
    setError('');
    setResult(null);
    setLoading(true);

    try {
      let res;

      if (tab === 'prd') {
        if (prdMode === 'file') {
          // ── File upload path ──────────────────────────────────────────────
          if (!prdFile) throw new Error('Please upload a PRD file (.docx, .pdf, .txt)');
          const form = new FormData();
          form.append('file', prdFile);
          form.append('project_name', projectName || 'My Project');
          res = await fetch(`${API_BASE}/upload/prd`, { method: 'POST', body: form });
        } else {
          // ── Paste path ────────────────────────────────────────────────────
          if (!prdText.trim()) throw new Error('Please paste your PRD content');
          res = await fetch(`${API_BASE}/generate/prd`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prd_text: prdText, project_name: projectName || 'My Project' }),
          });
        }
      } else {
        // ── Figma path ────────────────────────────────────────────────────
        if (!figmaUrl.trim()) throw new Error('Please enter a Figma URL');
        if (!figmaToken.trim()) throw new Error('Please enter your Figma access token');
        res = await fetch(`${API_BASE}/generate/figma`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ figma_url: figmaUrl, figma_token: figmaToken, project_name: projectName || 'My Project' }),
        });
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Server error');
      }

      const data = await res.json();
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [tab, prdMode, prdFile, prdText, figmaUrl, figmaToken, projectName]);

  const copyJSON = () => {
    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filterOptions = [
    { value: 'all', label: 'All' },
    { value: 'P0', label: 'P0 only' },
    { value: 'P1', label: 'P1 only' },
    { value: 'happy_path', label: 'Happy path' },
    { value: 'negative', label: 'Negative' },
    { value: 'edge_case', label: 'Edge cases' },
    { value: 'accessibility', label: 'Accessibility' },
  ];

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <div className="logo-icon"><Sparkles size={18} /></div>
            <span className="logo-text">TestWeave</span>
            <span className="logo-tag">AI QA</span>
          </div>
          <nav className="header-nav">
            <a href="https://github.com" target="_blank" rel="noreferrer" className="nav-link">
              <Github size={15} /> GitHub
            </a>
          </nav>
        </div>
      </header>

      <main className="main">
        {/* ── Hero ── */}
        {!result && (
          <div className="hero">
            <div className="hero-eyebrow"><Sparkles size={13} /> AI-Powered QA</div>
            <h1 className="hero-title">Generate test cases<br /><span className="accent">in seconds</span></h1>
            <p className="hero-sub">Upload a PRD doc or drop a Figma link. Get structured, prioritised test cases ready for Jira.</p>
            <div className="hero-features">
              <div className="feat"><BarChart3 size={14} />P0/P1/P2 priority</div>
              <div className="feat"><Shield size={14} />Accessibility checks</div>
              <div className="feat"><Bug size={14} />Negative + edge cases</div>
              <div className="feat"><Download size={14} />CSV / JSON export</div>
            </div>
          </div>
        )}

        {/* ── Input card ── */}
        <div className={`input-card ${result ? 'compact' : ''}`}>
          <div className="input-card-inner">

            {/* Project name */}
            <div className="field">
              <label className="field-label">Project name</label>
              <input
                className="field-input"
                placeholder="e.g. Checkout flow v2"
                value={projectName}
                onChange={e => setProjectName(e.target.value)}
              />
            </div>

            {/* Source tabs */}
            <div className="source-tabs">
              <button className={`source-tab ${tab === 'prd' ? 'active' : ''}`} onClick={() => setTab('prd')}>
                <FileText size={15} /> PRD / Doc
              </button>
              <button className={`source-tab ${tab === 'figma' ? 'active' : ''}`} onClick={() => setTab('figma')}>
                <Figma size={15} /> Figma design
              </button>
            </div>

            {/* ── PRD tab ── */}
            {tab === 'prd' && (
              <>
                {/* File vs paste toggle */}
                <div className="prd-mode-toggle">
                  <button
                    className={`mode-btn ${prdMode === 'file' ? 'active' : ''}`}
                    onClick={() => setPrdMode('file')}
                  >
                    <UploadCloud size={13} /> Upload file
                  </button>
                  <button
                    className={`mode-btn ${prdMode === 'paste' ? 'active' : ''}`}
                    onClick={() => setPrdMode('paste')}
                  >
                    <FilePlus size={13} /> Paste text
                  </button>
                </div>

                {prdMode === 'file' ? (
                  <DropZone
                    file={prdFile}
                    onFile={setPrdFile}
                    onClear={() => setPrdFile(null)}
                  />
                ) : (
                  <div className="field">
                    <label className="field-label">Paste PRD, user stories, or acceptance criteria</label>
                    <textarea
                      className="field-textarea"
                      placeholder={`## Login Screen\nUsers must be able to log in with email and password.\n\nAcceptance criteria:\n- Email must be valid format\n- Password minimum 8 characters\n- Show error on invalid credentials\n- Redirect to dashboard on success`}
                      value={prdText}
                      onChange={e => setPrdText(e.target.value)}
                      rows={10}
                    />
                    <div className="field-hint">{prdText.length.toLocaleString()} characters</div>
                  </div>
                )}
              </>
            )}

            {/* ── Figma tab ── */}
            {tab === 'figma' && (
              <>
                <div className="field">
                  <label className="field-label">Figma file URL</label>
                  <input
                    className="field-input"
                    placeholder="https://www.figma.com/file/XXXX/My-Design"
                    value={figmaUrl}
                    onChange={e => setFigmaUrl(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label className="field-label">
                    Figma personal access token
                    <a href="https://help.figma.com/hc/en-us/articles/8085703771159" target="_blank" rel="noreferrer" className="field-link">
                      How to get one <ArrowRight size={11} />
                    </a>
                  </label>
                  <input
                    className="field-input"
                    type="password"
                    placeholder="figd_..."
                    value={figmaToken}
                    onChange={e => setFigmaToken(e.target.value)}
                  />
                  <div className="field-hint">Token is never stored — sent directly to Figma API</div>
                </div>
              </>
            )}

            {/* Error */}
            {error && (
              <div className="error-box">
                <AlertCircle size={14} /> {error}
              </div>
            )}

            {/* Generate */}
            <button className="generate-btn" onClick={generate} disabled={loading}>
              {loading
                ? <><Loader2 size={16} className="spin" /> Generating test cases…</>
                : <><Sparkles size={16} /> Generate test cases</>
              }
            </button>
          </div>
        </div>

        {/* ── Results ── */}
        {result && (
          <div className="results">
            <div className="results-header">
              <div className="results-title-row">
                <CheckCircle size={18} className="success-icon" />
                <h2 className="results-title">{result.project}</h2>
                <span className="results-source">{result.source}</span>
                {result.filename && <span className="results-filename">{result.filename}</span>}
              </div>
              <StatsBar summary={result.summary} />
              <div className="results-actions">
                <div className="filter-row">
                  <Filter size={13} />
                  <select className="filter-select" value={filter} onChange={e => setFilter(e.target.value)}>
                    {filterOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <button className="action-btn" onClick={copyJSON}>
                  {copied ? <CheckCircle size={13} /> : <Copy size={13} />}
                  {copied ? 'Copied!' : 'Copy JSON'}
                </button>
                <button className="action-btn" onClick={() => downloadFile(toCSV(result), `${result.project}-testcases.csv`, 'text/csv')}>
                  <Download size={13} /> CSV
                </button>
                <button className="action-btn" onClick={() => downloadFile(JSON.stringify(result, null, 2), `${result.project}-testcases.json`, 'application/json')}>
                  <Download size={13} /> JSON
                </button>
              </div>
            </div>

            <div className="screens-list">
              {result.screens?.map((s, i) => <ScreenSection key={i} screen={s} filter={filter} />)}
            </div>

            <button className="regenerate-btn" onClick={() => setResult(null)}>
              <Sparkles size={14} /> Generate from a different source
            </button>
          </div>
        )}
      </main>

      <footer className="footer">
        Built with Claude + FastAPI + React · Deploy free on Render + Vercel
      </footer>
    </div>
  );
}

const API_BASE = process.env.REACT_APP_API_URL || '';

// ── Priority badge ────────────────────────────────────────────────────────────
function PriorityBadge({ p }) {
  const map = { P0: 'badge-p0', P1: 'badge-p1', P2: 'badge-p2' };
  return <span className={`badge ${map[p] || 'badge-p2'}`}>{p}</span>;
}

// ── Type badge ────────────────────────────────────────────────────────────────
function TypeBadge({ type }) {
  const map = {
    happy_path: { label: 'Happy path', cls: 'badge-happy' },
    negative: { label: 'Negative', cls: 'badge-negative' },
    edge_case: { label: 'Edge case', cls: 'badge-edge' },
    accessibility: { label: 'A11y', cls: 'badge-a11y' },
    performance: { label: 'Perf', cls: 'badge-perf' },
  };
  const { label, cls } = map[type] || { label: type, cls: 'badge-edge' };
  return <span className={`badge ${cls}`}>{label}</span>;
}

// ── Single test case card ─────────────────────────────────────────────────────
function TestCard({ tc }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`test-card ${open ? 'open' : ''}`}>
      <button className="test-card-header" onClick={() => setOpen(!open)}>
        <span className="tc-id">{tc.id}</span>
        <span className="tc-title">{tc.title}</span>
        <div className="tc-badges">
          <PriorityBadge p={tc.priority} />
          <TypeBadge type={tc.type} />
        </div>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <div className="test-card-body">
          {tc.component && (
            <div className="tc-row">
              <span className="tc-label">Component</span>
              <span className="tc-value mono">{tc.component}</span>
            </div>
          )}
          {tc.preconditions?.length > 0 && (
            <div className="tc-row">
              <span className="tc-label">Preconditions</span>
              <ul className="tc-list">
                {tc.preconditions.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}
          <div className="tc-row">
            <span className="tc-label">Steps</span>
            <ol className="tc-list ordered">
              {tc.steps?.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </div>
          <div className="tc-row">
            <span className="tc-label">Expected result</span>
            <span className="tc-expected">{tc.expected_result}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Screen section ────────────────────────────────────────────────────────────
function ScreenSection({ screen, filter }) {
  const cases = screen.test_cases?.filter(tc =>
    !filter || filter === 'all' || tc.priority === filter || tc.type === filter
  ) || [];
  if (cases.length === 0) return null;
  return (
    <div className="screen-section">
      <h3 className="screen-name">{screen.screen_name}</h3>
      <div className="tc-count">{cases.length} test cases</div>
      {cases.map(tc => <TestCard key={tc.id} tc={tc} />)}
    </div>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────
function StatsBar({ summary }) {
  if (!summary) return null;
  return (
    <div className="stats-bar">
      <div className="stat"><span className="stat-num">{summary.total}</span><span className="stat-label">Total</span></div>
      <div className="stat-divider" />
      <div className="stat"><span className="stat-num p0">{summary.p0}</span><span className="stat-label">P0</span></div>
      <div className="stat"><span className="stat-num p1">{summary.p1}</span><span className="stat-label">P1</span></div>
      <div className="stat"><span className="stat-num p2">{summary.p2}</span><span className="stat-label">P2</span></div>
      <div className="stat-divider" />
      <div className="stat"><span className="stat-num">{summary.happy_path}</span><span className="stat-label">Happy</span></div>
      <div className="stat"><span className="stat-num">{summary.negative}</span><span className="stat-label">Negative</span></div>
      <div className="stat"><span className="stat-num">{summary.edge_case}</span><span className="stat-label">Edge</span></div>
      <div className="stat"><span className="stat-num">{summary.accessibility}</span><span className="stat-label">A11y</span></div>
    </div>
  );
}

// ── Export helpers ────────────────────────────────────────────────────────────
function toCSV(data) {
  const rows = [['ID', 'Screen', 'Title', 'Type', 'Priority', 'Component', 'Preconditions', 'Steps', 'Expected Result']];
  data.screens?.forEach(s =>
    s.test_cases?.forEach(tc =>
      rows.push([
        tc.id, s.screen_name, tc.title, tc.type, tc.priority, tc.component || '',
        tc.preconditions?.join(' | ') || '',
        tc.steps?.join(' | ') || '',
        tc.expected_result,
      ])
    )
  );
  return rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
}

function downloadFile(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState('prd'); // 'prd' | 'figma'
  const [prdText, setPrdText] = useState('');
  const [figmaUrl, setFigmaUrl] = useState('');
  const [figmaToken, setFigmaToken] = useState('');
  const [projectName, setProjectName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [filter, setFilter] = useState('all');
  const [copied, setCopied] = useState(false);
  const [apiKey, setApiKey] = useState('');

  const generate = useCallback(async () => {
    setError('');
    setResult(null);
    setLoading(true);

    try {
      let endpoint, body;
      if (tab === 'prd') {
        if (!prdText.trim()) throw new Error('Please paste your PRD content');
        endpoint = '/generate/prd';
        body = { prd_text: prdText, project_name: projectName || 'My Project' };
      } else {
        if (!figmaUrl.trim()) throw new Error('Please enter a Figma URL');
        if (!figmaToken.trim()) throw new Error('Please enter your Figma access token');
        endpoint = '/generate/figma';
        body = { figma_url: figmaUrl, figma_token: figmaToken, project_name: projectName || 'My Project' };
      }

      const headers = { 'Content-Type': 'application/json' };
      if (apiKey) headers['x-api-key'] = apiKey;

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Server error');
      }

      const data = await res.json();
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [tab, prdText, figmaUrl, figmaToken, projectName, apiKey]);

  const copyJSON = () => {
    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filterOptions = [
    { value: 'all', label: 'All' },
    { value: 'P0', label: 'P0 only' },
    { value: 'P1', label: 'P1 only' },
    { value: 'happy_path', label: 'Happy path' },
    { value: 'negative', label: 'Negative' },
    { value: 'edge_case', label: 'Edge cases' },
    { value: 'accessibility', label: 'Accessibility' },
  ];

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <div className="logo-icon"><Sparkles size={18} /></div>
            <span className="logo-text">TestWeave</span>
            <span className="logo-tag">AI QA</span>
          </div>
          <nav className="header-nav">
            <a href="https://github.com" target="_blank" rel="noreferrer" className="nav-link">
              <Github size={15} /> GitHub
            </a>
          </nav>
        </div>
      </header>

      <main className="main">
        {/* ── Hero ── */}
        {!result && (
          <div className="hero">
            <div className="hero-eyebrow"><Sparkles size={13} /> AI-Powered QA</div>
            <h1 className="hero-title">Generate test cases<br /><span className="accent">in seconds</span></h1>
            <p className="hero-sub">Paste a PRD or drop a Figma link. Get structured, prioritised test cases ready for Jira.</p>
            <div className="hero-features">
              <div className="feat"><BarChart3 size={14} />P0/P1/P2 priority</div>
              <div className="feat"><Shield size={14} />Accessibility checks</div>
              <div className="feat"><Bug size={14} />Negative + edge cases</div>
              <div className="feat"><Download size={14} />CSV / JSON export</div>
            </div>
          </div>
        )}

        {/* ── Input card ── */}
        <div className={`input-card ${result ? 'compact' : ''}`}>
          <div className="input-card-inner">
            {/* Project name */}
            <div className="field">
              <label className="field-label">Project name</label>
              <input
                className="field-input"
                placeholder="e.g. Checkout flow v2"
                value={projectName}
                onChange={e => setProjectName(e.target.value)}
              />
            </div>

            {/* Source tabs */}
            <div className="source-tabs">
              <button
                className={`source-tab ${tab === 'prd' ? 'active' : ''}`}
                onClick={() => setTab('prd')}
              >
                <FileText size={15} /> PRD / Doc
              </button>
              <button
                className={`source-tab ${tab === 'figma' ? 'active' : ''}`}
                onClick={() => setTab('figma')}
              >
                <Figma size={15} /> Figma design
              </button>
            </div>

            {/* PRD tab */}
            {tab === 'prd' && (
              <div className="field">
                <label className="field-label">Paste your PRD, user stories, or acceptance criteria</label>
                <textarea
                  className="field-textarea"
                  placeholder={`Example:\n\n## Login Screen\nUsers must be able to log in with email and password.\nAcceptance criteria:\n- Email must be valid format\n- Password must be minimum 8 characters\n- Show error message on invalid credentials\n- Redirect to dashboard on success`}
                  value={prdText}
                  onChange={e => setPrdText(e.target.value)}
                  rows={10}
                />
                <div className="field-hint">{prdText.length.toLocaleString()} characters</div>
              </div>
            )}

            {/* Figma tab */}
            {tab === 'figma' && (
              <>
                <div className="field">
                  <label className="field-label">Figma file URL</label>
                  <input
                    className="field-input"
                    placeholder="https://www.figma.com/file/XXXX/My-Design"
                    value={figmaUrl}
                    onChange={e => setFigmaUrl(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label className="field-label">
                    Figma personal access token
                    <a
                      href="https://help.figma.com/hc/en-us/articles/8085703771159"
                      target="_blank"
                      rel="noreferrer"
                      className="field-link"
                    >
                      How to get one <ArrowRight size={11} />
                    </a>
                  </label>
                  <input
                    className="field-input"
                    type="password"
                    placeholder="figd_..."
                    value={figmaToken}
                    onChange={e => setFigmaToken(e.target.value)}
                  />
                  <div className="field-hint">Your token is never stored — sent directly to Figma API</div>
                </div>
              </>
            )}

            {/* Error */}
            {error && (
              <div className="error-box">
                <AlertCircle size={14} /> {error}
              </div>
            )}

            {/* Generate button */}
            <button
              className="generate-btn"
              onClick={generate}
              disabled={loading}
            >
              {loading ? (
                <><Loader2 size={16} className="spin" /> Generating test cases…</>
              ) : (
                <><Sparkles size={16} /> Generate test cases</>
              )}
            </button>
          </div>
        </div>

        {/* ── Results ── */}
        {result && (
          <div className="results">
            {/* Results header */}
            <div className="results-header">
              <div className="results-title-row">
                <CheckCircle size={18} className="success-icon" />
                <h2 className="results-title">{result.project}</h2>
                <span className="results-source">{result.source}</span>
              </div>
              <StatsBar summary={result.summary} />
              <div className="results-actions">
                <div className="filter-row">
                  <Filter size={13} />
                  <select
                    className="filter-select"
                    value={filter}
                    onChange={e => setFilter(e.target.value)}
                  >
                    {filterOptions.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <button className="action-btn" onClick={copyJSON}>
                  {copied ? <CheckCircle size={13} /> : <Copy size={13} />}
                  {copied ? 'Copied!' : 'Copy JSON'}
                </button>
                <button
                  className="action-btn"
                  onClick={() => downloadFile(toCSV(result), `${result.project}-testcases.csv`, 'text/csv')}
                >
                  <Download size={13} /> CSV
                </button>
                <button
                  className="action-btn"
                  onClick={() => downloadFile(JSON.stringify(result, null, 2), `${result.project}-testcases.json`, 'application/json')}
                >
                  <Download size={13} /> JSON
                </button>
              </div>
            </div>

            {/* Test case list */}
            <div className="screens-list">
              {result.screens?.map((s, i) => (
                <ScreenSection key={i} screen={s} filter={filter} />
              ))}
            </div>

            {/* Generate again */}
            <button className="regenerate-btn" onClick={() => setResult(null)}>
              <Sparkles size={14} /> Generate from a different source
            </button>
          </div>
        )}
      </main>

      <footer className="footer">
        Built with Claude + FastAPI + React &nbsp;·&nbsp; Deploy free on Render + Vercel
      </footer>
    </div>
  );
}
