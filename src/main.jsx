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
import './styles.css';

const models = [
  {
    id: 'fluxlm-base',
    rank: 1,
    name: 'FluxLM Base',
    lab: 'Latent Transport Lab',
    method: 'Flow matching',
    size: '410M',
    score: 1267,
    ci: '+/- 22',
    votes: 18420,
    winRate: 64,
    status: 'Public',
    color: 'green',
    blurb: 'A compact flow matching language model tuned for stable unconditional prose.',
  },
  {
    id: 'd3pm-large',
    rank: 2,
    name: 'D3PM Large',
    lab: 'Open Diffusion NLP',
    method: 'Discrete diffusion',
    size: '760M',
    score: 1238,
    ci: '+/- 24',
    votes: 17105,
    winRate: 61,
    status: 'Public',
    color: 'blue',
    blurb: 'A denoising diffusion baseline with strong paragraph-level fluency.',
  },
  {
    id: 'ar-control-350m',
    rank: 3,
    name: 'AR Control 350M',
    lab: 'Reference Baselines',
    method: 'Autoregressive',
    size: '350M',
    score: 1196,
    ci: '+/- 19',
    votes: 20991,
    winRate: 58,
    status: 'Public',
    color: 'amber',
    blurb: 'A likelihood-trained reference model included to calibrate human judgments.',
  },
  {
    id: 'maskgen-xl',
    rank: 4,
    name: 'MaskGen XL',
    lab: 'Sequence Modeling Group',
    method: 'Masked generation',
    size: '1.1B',
    score: 1154,
    ci: '+/- 31',
    votes: 9340,
    winRate: 54,
    status: 'Public',
    color: 'violet',
    blurb: 'A masked iterative generator with good local grammar and mixed global structure.',
  },
  {
    id: 'simplex-flow',
    rank: 5,
    name: 'Simplex Flow',
    lab: 'Submission Queue',
    method: 'Flow matching',
    size: '220M',
    score: 1109,
    ci: '+/- 36',
    votes: 6012,
    winRate: 51,
    status: 'Quota pending',
    color: 'slate',
    blurb: 'A new flow model awaiting researcher evaluation quota completion.',
  },
];

const battles = [
  {
    id: 'battle-1',
    leftModel: 'FluxLM Base',
    rightModel: 'D3PM Large',
    length: '256 tokens',
    domain: 'Open web mixture',
    left:
      'The cabinet of instruments stood beside the window, each drawer labeled in a handwriting that became smaller as the labels descended. Mara opened the third one and found not a tool but a set of instructions for listening: wait for the pipe to cool, count the interval between drops, then write down what the building refuses to say. At first she thought it was a joke left by the previous tenant. By midnight, when the radiator began answering in groups of five, she had filled three pages and stopped laughing.',
    right:
      'A map can be folded until the country is hidden, but the creases remember the roads. That was what Eli told the students before the storm took the power and the projector went dark. He continued anyway, drawing coastlines in chalk and asking them to imagine cities as agreements rather than places. Outside, the rain struck the roof with the bored patience of a clerk. Inside, nobody checked their phones for almost nine minutes.',
  },
  {
    id: 'battle-2',
    leftModel: 'MaskGen XL',
    rightModel: 'AR Control 350M',
    length: '192 tokens',
    domain: 'Fiction and essays',
    left:
      'The committee met every Tuesday to decide which sounds belonged in the archive. Bells were easy, as were engines, doors, applause, and the brittle scrape of winter branches. The trouble began with silence. Some members argued that silence was only the absence of eligible material. Others insisted it had dialects. By spring they had catalogued elevator pauses, hospital waiting rooms, and the hush after a name is said incorrectly.',
    right:
      'During the first week, the garden seemed to resist all interpretation. The tomatoes grew in spirals, the beans climbed downward, and the parsley appeared only in the path where everyone walked. Neighbors offered theories with the confidence of people who did not have to water it. Lena kept notes, then diagrams, then a calendar of improbable events. The garden, for its part, continued producing more cucumbers than any household could justify.',
  },
];

const methodStats = [
  { label: 'Flow', value: 42, color: 'green' },
  { label: 'Diffusion', value: 31, color: 'blue' },
  { label: 'Masked', value: 17, color: 'violet' },
  { label: 'AR baselines', value: 10, color: 'amber' },
];

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
    <>
      <Header route={route} menuOpen={menuOpen} setMenuOpen={setMenuOpen} />
      <main>{page}</main>
      <Footer />
    </>
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
              <FlaskConical size={15} /> Human preference benchmark
            </div>
            <h1>Rank likelihood-free language models by unconditional sample quality.</h1>
            <p>
              SampleBench turns blind pairwise human judgments into a public leaderboard for diffusion, flow
              matching, masked, and autoregressive language models.
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
          <div className="heroPanel" aria-label="Live leaderboard preview">
            <div className="panelHeader">
              <div>
                <span className="mutedLabel">Live ranking</span>
                <h2>Overall leaderboard</h2>
              </div>
              <span className="livePill">Mock data</span>
            </div>
            <LeaderboardTable compact />
          </div>
        </div>
      </section>
      <section className="container sectionGrid">
        <MetricCard icon={<Users />} label="Human votes" value="71,868" detail="Blind comparisons across public and pending models" />
        <MetricCard icon={<Trophy />} label="Active models" value="24" detail="Diffusion, flow, masked, and AR references" />
        <MetricCard icon={<ClipboardList />} label="Submission rule" value="Give to enter" detail="Researchers evaluate samples before their models rank" />
      </section>
      <section className="container twoColumnSection">
        <div>
          <div className="eyebrow">
            <BookOpen size={15} /> Built for unconditional generation
          </div>
          <h2 className="sectionTitle">No prompts, no chat transcript, no perplexity proxy.</h2>
          <p className="sectionText">
            Evaluators compare two anonymous samples generated under the same length and corpus setting. The
            interface rewards careful reading while preserving the throughput needed for a credible leaderboard.
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
    'Leaderboard and model page refresh',
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
          <p>{battle.domain} | {battle.length} | model names hidden until vote</p>
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
        title="Human preference rankings"
        text="Scores are derived from blind pairwise comparisons of unconditional generations. Confidence intervals and vote counts are shown beside every model."
      />
      <Tabs items={['Overall', 'Flow', 'Diffusion', 'Masked', 'AR baselines']} />
      <div className="leaderboardLayout">
        <section className="tablePanel">
          <LeaderboardTable />
        </section>
        <aside className="sidePanel">
          <h3>Method mix</h3>
          {methodStats.map((stat) => <StatBar key={stat.label} {...stat} />)}
          <div className="noteBox">
            <Info size={17} /> Rankings hide pending submissions until quota and minimum votes are met.
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
        title="Submitted generators"
        text="Browse model metadata, evaluation status, and public sample records."
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
        <InfoTile label="Size" value={model.size} />
        <InfoTile label="Win rate" value={`${model.winRate}%`} />
        <InfoTile label="Status" value={model.status} />
      </div>
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
        text="Generative perplexity can fail to reflect sample quality for models that do not expose tractable likelihoods. SampleBench instead asks humans to judge the text users actually read."
      />
      <div className="textPanel">
        <h2>Evaluation protocol</h2>
        <p>Each comparison displays two anonymous samples generated under matched settings. Evaluators choose the better sample, a tie, both bad, or skip. Aggregation can use Bradley-Terry or Elo-style updates with uncertainty intervals.</p>
        <h2>Researcher incentive</h2>
        <p>Groups that submit models complete evaluation quotas for the shared pool. This turns evaluation labor into the currency for appearing on the leaderboard.</p>
        <h2>Frontend scope</h2>
        <p>This prototype defines the public product surface: leaderboard, voting, model pages, submission, and methodology copy. It uses mock data until the backend schema is finalized.</p>
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
  const rows = compact ? models.slice(0, 4) : models;
  return (
    <div className="tableWrap">
      <table className="leaderboardTable">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Model</th>
            <th>Method</th>
            <th>Score</th>
            {!compact && <th>Votes</th>}
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((model) => (
            <tr key={model.id}>
              <td><span className="rankCell"><Medal size={15} /> {model.rank}</span></td>
              <td><a href={`#/models/${model.id}`} className="modelLink">{model.name}<small>{model.lab}</small></a></td>
              <td><span className={`methodPill ${model.color}`}>{model.method}</span></td>
              <td><strong>{model.score}</strong><small>{model.ci}</small></td>
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
    <a className="modelCard" href={`#/models/${model.id}`}>
      <div className="modelCardTop">
        <span className="rankBadge">#{model.rank}</span>
        <span className="statusPill">{model.status}</span>
      </div>
      <h2>{model.name}</h2>
      <p>{model.blurb}</p>
      <div className="modelMeta">
        <span>{model.method}</span>
        <span>{model.size}</span>
        <span>{model.votes.toLocaleString()} votes</span>
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
