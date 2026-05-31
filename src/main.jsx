import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  FlaskConical,
  GitCompareArrows,
  Info,
  Medal,
  Menu,
  Send,
  Sparkles,
  Trophy,
  Users,
  X,
} from 'lucide-react';
import { battles, checkpointFamilies, checkpointRoot, methodStats, models, sampleRoot } from './data.js';
import './styles.css';

function getRoute() {
  return window.location.hash.replace(/^#\/?/, '') || 'home';
}

function App() {
  const [route, setRoute] = useState(getRoute());
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onHash = () => {
      setRoute(getRoute());
      setMenuOpen(false);
      window.scrollTo({ top: 0, behavior: 'instant' });
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const page = useMemo(() => {
    if (route.startsWith('models/')) return <ModelDetail id={route.split('/')[1]} />;
    if (route === 'vote') return <VotePage />;
    if (route === 'leaderboard') return <LeaderboardPage />;
    if (route === 'models') return <ModelsPage />;
    if (route === 'submit') return <SubmitPage />;
    if (route === 'about') return <AboutPage />;
    return <HomePage />;
  }, [route]);

  return (
    <div className="appShell">
      <SideRail route={route} />
      <Header route={route} menuOpen={menuOpen} setMenuOpen={setMenuOpen} />
      <main className="mainPane">{page}</main>
      <Footer />
    </div>
  );
}

function SideRail({ route }) {
  const links = [
    ['home', 'Overview', <BarChart3 size={18} />],
    ['vote', 'New Battle', <GitCompareArrows size={18} />],
    ['leaderboard', 'Leaderboard', <Trophy size={18} />],
    ['models', 'Models', <FlaskConical size={18} />],
    ['submit', 'Submit', <Send size={18} />],
  ];

  return (
    <aside className="sideRail">
      <a className="sideLogo" href="#/home">SampleBench</a>
      <nav>
        {links.map(([href, label, icon]) => (
          <a key={href} className={route === href ? 'active' : ''} href={`#/${href}`}>
            {icon}
            <span>{label}</span>
          </a>
        ))}
      </nav>
      <div className="railCard">
        <strong>OWT evaluation</strong>
        <p>{models.length} sample sets from `lm-bench/results/samples/owt`.</p>
        <a href="#/vote">Start Voting</a>
      </div>
    </aside>
  );
}

function Header({ route, menuOpen, setMenuOpen }) {
  const links = [
    ['vote', 'Vote'],
    ['leaderboard', 'Leaderboard'],
    ['models', 'Models'],
    ['submit', 'Submit'],
    ['about', 'About'],
  ];

  return (
    <header className="topbar">
      <a className="brand" href="#/home" aria-label="SampleBench home">
        <span className="brandMark">
          <GitCompareArrows size={18} />
        </span>
        <span>SampleBench</span>
      </a>
      <nav className={menuOpen ? 'nav open' : 'nav'}>
        {links.map(([href, label]) => (
          <a key={href} className={route === href ? 'active' : ''} href={`#/${href}`}>
            {label}
          </a>
        ))}
      </nav>
      <div className="topActions">
        <a className="ghostButton hideSmall" href="#/leaderboard">
          <BarChart3 size={16} /> Rankings
        </a>
        <a className="primaryButton hideSmall" href="#/vote">
          <Sparkles size={16} /> Start Voting
        </a>
        <button className="iconButton menuButton" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle menu">
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
    </header>
  );
}

function HomePage() {
  return (
    <div>
      <section className="heroBand">
        <div className="heroGrid container">
          <div className="heroCopy">
            <div className="eyebrow">
              <FlaskConical size={15} /> OWT human preference benchmark
            </div>
            <h1>Experience the frontier of likelihood-free language model evaluation.</h1>
            <p>
              SampleBench compares real unconditional samples from the OWT checkpoints and sample suites in
              lm-bench, using blind human preference instead of generative perplexity alone.
            </p>
            <div className="heroActions">
              <a className="primaryButton large" href="#/vote">
                Start Voting <ArrowRight size={18} />
              </a>
              <a className="ghostButton large" href="#/submit">
                Submit Model <Send size={18} />
              </a>
            </div>
          </div>
          <div className="heroPanel narrativePanel" aria-label="SampleBench narrative">
            <div className="panelHeader">
              <div>
                <span className="mutedLabel">Why SampleBench exists</span>
                <h2>A measurement gap is opening.</h2>
              </div>
            </div>
            <div className="storyList">
              <p>
                Continuous-time flow and diffusion language models are becoming credible generators, but many do
                not expose tractable likelihoods, so validation perplexity no longer gives the field a shared yardstick.
              </p>
              <p>
                Generative perplexity has become the default fallback for unconditional generation, but it is a fragile
                proxy for what people actually see in samples.
              </p>
              <p>
                SampleBench makes blind human comparison scalable, so progress can be tracked by preference over real
                generated text rather than by a single flawed proxy metric.
              </p>
            </div>
          </div>
        </div>
      </section>
      <section className="container sectionGrid">
        <MetricCard icon={<Users />} label="OWT sample sets" value={String(models.length)} detail={`Loaded from ${sampleRoot}`} />
        <MetricCard icon={<Trophy />} label="Checkpoint families" value={String(checkpointFamilies.length)} detail={`Discovered under ${checkpointRoot}`} />
        <MetricCard icon={<ClipboardList />} label="Submission rule" value="Give to enter" detail="Researchers evaluate samples before their models rank" />
      </section>
      <section className="container twoColumnSection">
        <div>
          <div className="eyebrow">
            <BookOpen size={15} /> Built for unconditional generation
          </div>
          <h2 className="sectionTitle">The target is unconditional sample quality, judged directly.</h2>
          <p className="sectionText">
            Evaluators compare two anonymous samples generated under matched OWT settings. Aggregated choices become
            a leaderboard that can include flow, diffusion, and masked generators without forcing them through
            likelihood-based evaluation.
          </p>
        </div>
        <WorkflowCard />
      </section>
    </div>
  );
}

function MetricCard({ icon, label, value, detail }) {
  return (
    <article className="metricCard">
      <div className="metricIcon">{React.cloneElement(icon, { size: 19 })}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function WorkflowCard() {
  const steps = [
    'Blind pair generated',
    'Human chooses A, B, tie, or both bad',
    'Preference update with uncertainty',
    'Model ranking updates',
  ];
  return (
    <div className="workflowCard">
      {steps.map((step, index) => (
        <div className="workflowStep" key={step}>
          <span>{index + 1}</span>
          <p>{step}</p>
        </div>
      ))}
    </div>
  );
}

function VotePage() {
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState(null);
  const battle = battles[index % battles.length];
  const choices = [
    ['left', 'A is better'],
    ['tie', 'Tie'],
    ['right', 'B is better'],
    ['bad', 'Both bad'],
  ];

  return (
    <div className="voteShell container">
      <div className="voteHeader">
        <div>
          <div className="eyebrow">
            <GitCompareArrows size={15} /> Blind battle
          </div>
          <h1>Which sample is better?</h1>
          <p>{battle.domain} | {battle.length} | samples from lm-bench/results/samples/owt</p>
        </div>
        <a className="ghostButton" href="#/leaderboard">
          <BarChart3 size={16} /> View rankings
        </a>
      </div>
      <div className="sampleGrid">
        <SamplePane label="Sample A" text={battle.left} revealed={selected} model={battle.leftModel} />
        <SamplePane label="Sample B" text={battle.right} revealed={selected} model={battle.rightModel} />
      </div>
      <div className="voteDock" aria-label="Voting controls">
        <div className="rubricStrip">
          <span>Coherence</span>
          <span>Fluency</span>
          <span>Originality</span>
          <span>Low repetition</span>
        </div>
        <div className="voteButtons">
          {choices.map(([key, label]) => (
            <button key={key} className={selected === key ? 'voteButton selected' : 'voteButton'} onClick={() => setSelected(key)}>
              {selected === key && <Check size={16} />}
              {label}
            </button>
          ))}
          <button className="primaryButton" onClick={() => { setSelected(null); setIndex(index + 1); }}>
            Next Pair <ChevronRight size={17} />
          </button>
        </div>
      </div>
    </div>
  );
}

function SamplePane({ label, text, revealed, model }) {
  return (
    <article className="samplePane">
      <div className="sampleTop">
        <span>{label}</span>
        <span className="sampleTag">Anonymous</span>
      </div>
      <p>{text}</p>
      {revealed && (
        <div className="revealBox">
          Model: <strong>{model}</strong>
        </div>
      )}
    </article>
  );
}

function LeaderboardPage() {
  return (
    <div className="container pageStack">
      <PageTitle
        icon={<Trophy size={18} />}
        label="Leaderboard"
        title="OWT leaderboard overview"
        text="The rows use OWT checkpoint labels and sample files from the current lm-bench tree. The displayed preference scores are placeholders until collected human votes replace the frontend prototype data."
      />
      <Tabs items={['Overall', 'Flow', 'Diffusion']} />
      <div className="leaderboardLayout">
        <section className="tablePanel">
          <LeaderboardTable />
        </section>
        <aside className="sidePanel">
          <h3>Method mix</h3>
          {methodStats.map((stat) => <StatBar key={stat.label} {...stat} />)}
          <div className="noteBox">
            <Info size={17} /> Sample text is loaded from the OWT JSONL files; checkpoint paths come from the matching manifests.
          </div>
        </aside>
      </div>
    </div>
  );
}

function ModelsPage() {
  return (
    <div className="container pageStack">
      <PageTitle
        icon={<FlaskConical size={18} />}
        label="Models"
        title="Continuous-generation papers"
        text="Each card links to the corresponding arXiv PDF for the model family represented by the OWT samples."
      />
      <div className="modelGrid">
        {models.map((model) => <ModelCard key={model.id} model={model} />)}
      </div>
    </div>
  );
}

function ModelDetail({ id }) {
  const model = models.find((m) => m.id === id) || models[0];
  return (
    <div className="container pageStack">
      <a className="backLink" href="#/models">Back to models</a>
      <section className="modelHero">
        <div>
          <div className="rankBadge">#{model.rank}</div>
          <h1>{model.name}</h1>
          <p>{model.blurb}</p>
        </div>
        <div className="scoreCard">
          <span>Preference score</span>
          <strong>{model.score}</strong>
          <small>{model.ci} across {model.votes.toLocaleString()} votes</small>
        </div>
      </section>
      <div className="detailGrid">
        <InfoTile label="Method" value={model.method} />
        <InfoTile label="Sample length" value={model.size} />
        <InfoTile label="Gen PPL" value={model.genPpl} />
        <InfoTile label="Status" value={model.status} />
      </div>
      <section className="textPanel pathPanel">
        <h2>Source paths</h2>
        <p><strong>Checkpoint:</strong> {model.checkpoint}</p>
        <p><strong>Sample suite:</strong> {sampleRoot}/owt_L1024_paper/{model.id}/samples.jsonl</p>
      </section>
      <section className="tablePanel detailTable">
        <h2>Head-to-head snapshot</h2>
        <LeaderboardTable compact />
      </section>
    </div>
  );
}

function SubmitPage() {
  return (
    <div className="container pageStack narrow">
      <PageTitle
        icon={<Send size={18} />}
        label="Submit"
        title="Bring a model, contribute evaluations"
        text="SampleBench uses a give-to-enter incentive: every submitting group must complete blinded evaluations before their model becomes public."
      />
      <form className="submitForm">
        <label>Model name<input placeholder="e.g. FluxLM Base" /></label>
        <label>Research group<input placeholder="Lab, institute, or team" /></label>
        <label>
          Generation method
          <select defaultValue="Flow matching">
            <option>Flow matching</option>
            <option>Discrete diffusion</option>
            <option>Masked generation</option>
            <option>Autoregressive baseline</option>
          </select>
        </label>
        <label>Public paper or report<input placeholder="URL or arXiv id" /></label>
        <label>Sample policy<textarea placeholder="Describe sampling temperature, steps, length, and filtering." /></label>
        <button type="button" className="primaryButton large">
          Request Review <ArrowRight size={18} />
        </button>
      </form>
      <div className="noteBox">
        <CircleHelp size={17} /> Prototype form only. Backend submission and identity checks would be added after the frontend contract is approved.
      </div>
    </div>
  );
}

function AboutPage() {
  return (
    <div className="container pageStack narrow">
      <PageTitle
        icon={<Info size={18} />}
        label="Methodology"
        title="Why human preference, and why unconditional samples?"
        text="The site is a frontend prototype for replacing proxy-only evaluation with scalable blind human preference over unconditional samples."
      />
      <div className="textPanel">
        <h2>The evaluation problem</h2>
        <p>A new wave of continuous-based flow and diffusion language models is changing what language modeling looks like. These models can generate text without exposing the same tractable likelihood interface as classic autoregressive models, so validation perplexity cannot remain the universal scoreboard.</p>
        <h2>Why generative perplexity is not enough</h2>
        <p>Generative perplexity became the de facto metric for unconditional generation quality because it is easy to compute after samples exist. But it compresses a complicated human judgment into a brittle proxy: coherence, repetition, local fluency, topic drift, and factual shape can move in ways the metric does not faithfully capture.</p>
        <h2>The SampleBench bet</h2>
        <p>SampleBench treats the generated text itself as the object of evaluation. Humans compare anonymous samples produced under matched settings, and the aggregate preference signal becomes the public ranking. The goal is not to replace careful papers; it is to give the field a scalable, shared view of whether samples are actually getting better.</p>
        <h2>Incentive design</h2>
        <p>Researchers who want their models represented contribute evaluations to the shared pool. That keeps the leaderboard alive, makes evaluation labor visible, and aligns participation with improving the benchmark rather than only appearing on it.</p>
      </div>
    </div>
  );
}

function PageTitle({ icon, label, title, text }) {
  return (
    <section className="pageTitle">
      <div className="eyebrow">{icon}{label}</div>
      <h1>{title}</h1>
      <p>{text}</p>
    </section>
  );
}

function Tabs({ items }) {
  return <div className="tabs">{items.map((item, index) => <button className={index === 0 ? 'active' : ''} key={item}>{item}</button>)}</div>;
}

function LeaderboardTable({ compact = false }) {
  const leaderboardModels = models.filter((model) => ['flow', 'diffusion'].includes(model.family));
  const rows = compact ? leaderboardModels.slice(0, 4) : leaderboardModels;
  return (
    <div className="tableWrap">
      <table className="leaderboardTable">
        <thead>
            <tr>
              <th>Rank</th>
              <th>Model</th>
              <th>Score</th>
              {!compact && <th>Votes</th>}
              <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((model) => (
            <tr key={model.id}>
              <td><span className="rankCell"><Medal size={15} /> {model.rank}</span></td>
              <td>
                <a href={model.paperUrl} className="modelLink" target="_blank" rel="noreferrer">
                  {model.name}
                  <small>{model.method} · {model.checkpoint}</small>
                </a>
              </td>
              <td>
                <div className="scoreVisual">
                  <span style={{ width: `${Math.max(18, Math.min(100, (model.score - 1300) / 2.2))}%` }} />
                  <strong>{model.score}</strong>
                  <small>{model.ci}</small>
                </div>
              </td>
              {!compact && <td>{model.votes.toLocaleString()}</td>}
              <td><span className="statusPill">{model.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelCard({ model }) {
  return (
    <a className="modelCard" href={model.paperUrl} target="_blank" rel="noreferrer">
      <div className="modelCardTop">
        <span className="rankBadge">#{model.rank}</span>
        <span className="statusPill">{model.status}</span>
      </div>
      <h2>{model.name}</h2>
      <p>{model.blurb}</p>
      <div className="modelMeta">
        <span>{model.method}</span>
        <span>{model.size}</span>
        <span>{model.genPpl} gen-ppl</span>
      </div>
    </a>
  );
}

function StatBar({ label, value, color }) {
  return (
    <div className="statBar">
      <div><span>{label}</span><strong>{value}%</strong></div>
      <div className="barTrack"><span className={color} style={{ width: `${value}%` }} /></div>
    </div>
  );
}

function InfoTile({ label, value }) {
  return <div className="infoTile"><span>{label}</span><strong>{value}</strong></div>;
}

function Footer() {
  return (
    <footer className="footer container">
      <span>SampleBench</span>
      <span>Human preference evaluation for unconditional language generation.</span>
    </footer>
  );
}

createRoot(document.getElementById('root')).render(<App />);
