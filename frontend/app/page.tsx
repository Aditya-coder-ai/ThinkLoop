"use client";

import { useEffect, useState } from "react";
import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  ArrowDown,
  ArrowUpRight,
  BrainCircuit,
  Check,
  CircleDot,
  Compass,
  Eye,
  Layers3,
  Lightbulb,
  Moon,
  Sun,
} from "lucide-react";
import { ScrollProgressStroke } from "./components/ScrollProgressStroke";

const loopSteps = [
  {
    number: "01",
    label: "Start with a question",
    title: "Interactive learning",
    body: "Pick a topic and begin a conversation that feels less like a worksheet and more like a thoughtful study partner.",
    prompt: "Why does the graph turn here?",
    response: "Let’s slow down. What changes in the equation at that point?",
    color: "clay",
  },
  {
    number: "02",
    label: "Listen for the why",
    title: "Reasoning analysis",
    body: "Thinkloop pays attention to your explanation, confidence, and recurring patterns — not only the answer you submit.",
    prompt: "I think the slope is 4 because 8 ÷ 2 = 4.",
    response: "You’re close. Which two values did you compare?",
    color: "olive",
  },
  {
    number: "03",
    label: "Find the snag",
    title: "Cognitive friction detection",
    body: "It surfaces the missing prerequisite or misconception that is making the current idea feel harder than it should.",
    prompt: "Quadratics keep falling apart for me.",
    response: "Your factoring is solid. The friction starts one step earlier: signed numbers.",
    color: "ochre",
  },
  {
    number: "04",
    label: "Change the next move",
    title: "Personalized guidance",
    body: "Get a precise hint, a better question, or one concept to revisit — the smallest useful intervention, at the right time.",
    prompt: "So I should go back to algebra?",
    response: "Just one piece: negative coefficients. Try this two-minute warm-up.",
    color: "sage",
  },
  {
    number: "05",
    label: "Prove it to yourself",
    title: "Progress & mastery tracking",
    body: "Your learner profile grows from evidence. Revisit the idea, test the change, and see understanding become more reliable.",
    prompt: "I can explain it without the hint now.",
    response: "That’s a new signal. Your quadratic reasoning is ready for the next layer.",
    color: "ink",
  },
];

const features = [
  {
    icon: BrainCircuit,
    index: "01",
    title: "Socratic AI mentor",
    description: "A patient conversation that keeps the work yours. Thinkloop asks before it explains.",
  },
  {
    icon: Eye,
    index: "02",
    title: "Cognitive friction engine",
    description: "A live hypothesis about where understanding is snagging — so practice can become specific.",
  },
  {
    icon: Layers3,
    index: "03",
    title: "Knowledge graph",
    description: "A visual map of concepts and prerequisites that makes the shape of a subject easier to see.",
  },
  {
    icon: CircleDot,
    index: "04",
    title: "Learner memory",
    description: "Previous attempts, mistakes, and breakthroughs stay in the room for a more useful next session.",
  },
  {
    icon: Compass,
    index: "05",
    title: "Adaptive learning paths",
    description: "A next step chosen for your actual needs, not a generic course sequence.",
  },
  {
    icon: Lightbulb,
    index: "06",
    title: "Progress dashboard",
    description: "See strengths, open loops, and confidence change without reducing learning to a single score.",
  },
];

const audiences = [
  { name: "School students", detail: "Build foundations that last", mark: "A" },
  { name: "College students", detail: "Connect concepts to practice", mark: "B" },
  { name: "Exam aspirants", detail: "Diagnose the weak link", mark: "C" },
  { name: "Independent learners", detail: "Learn on your own terms", mark: "D" },
];

function Reveal({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

export default function Home() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [activeStep, setActiveStep] = useState(0);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const saved = window.localStorage.getItem("thinkloop-theme") as "light" | "dark" | null;
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const nextTheme = saved ?? preferred;
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem("thinkloop-theme", nextTheme);
  };

  const step = loopSteps[activeStep];

  return (
    <main className="site-main">
      <ScrollProgressStroke />
      <header className="site-header">
        <nav className="site-nav" aria-label="Main navigation">
          <a className="wordmark" href="#top" aria-label="Thinkloop home">
            <span className="wordmark-symbol" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <span className="wordmark-text">thinkloop</span>
          </a>

          <div className="nav-links">
            <a href="#method" className="nav-link">The method</a>
            <a href="#features" className="nav-link">What it notices</a>
            <a href="#mvp" className="nav-link">MVP</a>
            <a href="/workspace" className="nav-link nav-link-workspace">
              <span>Workspace</span>
              <span className="workspace-badge-dot" />
            </a>
          </div>

          <div className="nav-actions">
            <button
              className="theme-toggle"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            >
              {theme === "light" ? <Moon size={14} strokeWidth={2} /> : <Sun size={14} strokeWidth={2} />}
              <span className="theme-toggle-label">{theme === "light" ? "Night" : "Day"}</span>
            </button>

            <SignedOut>
              <a href="/sign-in" className="nav-btn-ghost">
                Sign In
              </a>
              <a href="https://think-loop-mu.vercel.app/sign-up" className="nav-btn-primary">
                <span>Get Started</span>
                <ArrowUpRight size={14} strokeWidth={2.2} />
              </a>
            </SignedOut>

            <SignedIn>
              <a href="/workspace" className="nav-btn-primary nav-btn-workspace">
                <span>Open Workspace</span>
                <ArrowUpRight size={14} strokeWidth={2.2} />
              </a>
              <div className="user-button-wrapper">
                <UserButton
                  afterSignOutUrl="/"
                  appearance={{
                    elements: {
                      userButtonAvatarBox: "w-8 h-8 rounded-full border border-[var(--line-strong)]",
                    },
                  }}
                />
              </div>
            </SignedIn>
          </div>
        </nav>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <Reveal>
            <div className="eyebrow"><span className="eyebrow-dot" /> Cognitive learning, rethought</div>
          </Reveal>
          <Reveal delay={0.08}>
            <h1>Learn the way<br /><em>your mind works.</em></h1>
          </Reveal>
          <Reveal delay={0.16}>
            <p className="hero-intro">Thinkloop is a personal cognitive mentor for students who want more than an answer. It helps you notice the thinking behind the work — then makes the next step feel possible.</p>
          </Reveal>
          <Reveal delay={0.24}>
            <div className="hero-actions">
              <a className="button button-primary" href="/workspace">Launch Workspace <ArrowUpRight size={16} /></a>
              <a className="text-link" href="#method">Explore the method <ArrowDown size={16} /></a>
            </div>
          </Reveal>
          <Reveal delay={0.32}>
            <div className="hero-note"><span>Built for the moment between “I don’t get it” and “oh, I see.”</span><span className="note-line" /></div>
          </Reveal>
        </div>

        <Reveal className="hero-visual" delay={0.18}>
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
          <motion.div className="thinking-card" animate={{ y: [0, -9, 0], rotate: [0, 0.5, 0] }} transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}>
            <div className="card-topline"><span>LIVE SESSION / 02</span><span className="status-pill"><span /> Listening</span></div>
            <div className="card-topic"><span className="topic-kicker">PHYSICS / MOTION</span><strong>What changed<br />at the turning point?</strong></div>
            <div className="card-axis"><span className="axis-y">velocity</span><div className="graph"><span className="graph-line" /><span className="graph-point p1" /><span className="graph-point p2" /><span className="graph-point p3" /><span className="graph-label label-one">−2</span><span className="graph-label label-two">0</span><span className="graph-label label-three">+2</span></div><span className="axis-x">time →</span></div>
            <div className="card-answer"><div className="avatar-mark">you</div><p>It slows down, then changes direction.</p><Check size={16} /></div>
            <div className="card-hint"><span className="hint-mark">?</span><span>That’s a strong observation. What would the velocity be at the exact point where direction changes?</span></div>
          </motion.div>
          <div className="hero-stamp"><span>think</span><span>in</span><span>loops</span></div>
          <div className="hero-caption"><span>01 / 05</span><span>Small questions.<br />Durable understanding.</span></div>
        </Reveal>
      </section>

      <section className="proof-strip" aria-label="Thinkloop principles">
        <span>Less answer machine</span><i>•</i><span>More thinking partner</span><i>•</i><span>Made for real understanding</span>
      </section>

      <section className="section intro-section" id="difference">
        <div className="section-label"><span>01</span><span>Why this exists</span></div>
        <div className="intro-grid">
          <Reveal><h2>Most tools measure <em>what</em> you got wrong. Thinkloop looks for <em>why.</em></h2></Reveal>
          <Reveal delay={0.1}><div className="intro-body"><p>Traditional learning rewards completion: finish the syllabus, memorize the formula, move to the next chapter. But a correct answer can hide a shaky mental model — and a wrong answer can hide a very good question.</p><p>Thinkloop is designed around that gap. It studies your reasoning, finds the friction, and gives you the smallest useful nudge to keep going.</p><a className="text-link" href="#method">Follow the cognitive loop <ArrowUpRight size={16} /></a></div></Reveal>
        </div>
        <div className="comparison-row">
          <div className="comparison-old"><span className="comparison-tag">THE OLD LOOP</span><div className="comparison-flow"><strong>Question</strong><span>→</span><strong>Answer</strong><span>→</span><strong>Score</strong></div><p>Did you get it right?</p></div>
          <div className="comparison-new"><span className="comparison-tag">THE THINKLOOP</span><div className="comparison-flow"><strong>Question</strong><span>→</span><strong>Reasoning</strong><span>→</span><strong>Insight</strong></div><p>What will help you understand?</p></div>
        </div>
      </section>

      <section className="section method-section" id="method">
        <div className="section-label"><span>02</span><span>The cognitive learning loop</span></div>
        <div className="method-heading"><Reveal><h2>Understanding isn’t a straight line.<br /><em>It’s a practice.</em></h2></Reveal><Reveal delay={0.1}><p>Thinkloop keeps returning to the part that matters: your thinking. Select a step to see how the experience changes in real time.</p></Reveal></div>
        <div className="loop-interface">
          <div className="loop-rail">
            <div className="loop-progress" aria-hidden="true"><motion.span animate={{ scaleY: prefersReducedMotion ? 1 : (activeStep + 1) / loopSteps.length }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }} /></div>
            {loopSteps.map((item, index) => (
              <motion.button className={`loop-step ${activeStep === index ? "active" : ""}`} key={item.number} onClick={() => setActiveStep(index)} aria-pressed={activeStep === index} whileHover={prefersReducedMotion ? undefined : { x: 4 }} whileTap={prefersReducedMotion ? undefined : { scale: 0.985 }} transition={{ duration: 0.18 }}>
                {activeStep === index && <motion.span className="step-active-fill" layoutId="active-step-fill" transition={{ type: "spring", stiffness: 420, damping: 32 }} />}
                <span className="step-number">{item.number}</span><span className="step-copy"><strong>{item.title}</strong><small>{item.label}</small></span><motion.span className="step-arrow" animate={activeStep === index && !prefersReducedMotion ? { opacity: 1, x: 0, rotate: 0 } : { opacity: 0, x: -5, rotate: -12 }} transition={{ duration: 0.2 }}>↗</motion.span>
              </motion.button>
            ))}
          </div>
          <div className={`loop-stage stage-${step.color}`}>
            <AnimatePresence mode="wait">
              <motion.div key={step.number} className="stage-content" initial={{ opacity: 0, x: prefersReducedMotion ? 0 : 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: prefersReducedMotion ? 0 : -16 }} transition={{ duration: prefersReducedMotion ? 0 : 0.34, ease: [0.22, 1, 0.36, 1] }}>
                <div className="stage-kicker">STEP {step.number} / {step.label}</div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
                <div className="conversation">
                  <motion.div className="conversation-line student" initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: prefersReducedMotion ? 0 : 0.1, duration: 0.28 }}><span className="speaker">YOU</span><span>{step.prompt}</span></motion.div>
                  <motion.div className="conversation-line mentor" initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: prefersReducedMotion ? 0 : 0.19, duration: 0.3 }}><span className="speaker">THINKLOOP</span><span>{step.response}</span></motion.div>
                </div>
              </motion.div>
            </AnimatePresence>
            <motion.div className="stage-orbit" aria-hidden="true" animate={prefersReducedMotion ? undefined : { rotate: [33, 38, 33], scale: [1, 1.025, 1] }} transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}><span /><span /><span /><span /></motion.div>
            <motion.div className="stage-counter" key={step.number} initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 8 }} animate={{ opacity: 0.32, y: 0 }} transition={{ duration: 0.35 }}>{step.number}<span>/05</span></motion.div>
          </div>
        </div>
      </section>

      <section className="section features-section" id="features">
        <div className="section-label"><span>03</span><span>What it notices</span></div>
        <div className="features-heading"><Reveal><h2>A better picture of<br /><em>how you learn.</em></h2></Reveal><Reveal delay={0.1}><p>Six connected capabilities, built around the learner’s reasoning rather than the platform’s content library.</p></Reveal></div>
        <div className="feature-grid">
          {features.map((feature, index) => { const Icon = feature.icon; return <Reveal key={feature.index} delay={index * 0.04}><article className="feature-card"><div className="feature-card-top"><span>{feature.index}</span><Icon size={21} strokeWidth={1.5} /></div><h3>{feature.title}</h3><p>{feature.description}</p><span className="feature-line" /></article></Reveal>; })}
        </div>
      </section>

      <section className="audience-section">
        <div className="audience-aside"><div className="section-label"><span>04</span><span>Made for learners</span></div><h2>Wherever you are in the <em>loop.</em></h2><p>From foundational concepts to high-stakes preparation, Thinkloop meets learners at the level of their questions.</p></div>
        <div className="audience-list">{audiences.map((audience, index) => <Reveal key={audience.mark} delay={index * 0.07}><div className="audience-item"><span className="audience-mark">{audience.mark}</span><div><h3>{audience.name}</h3><p>{audience.detail}</p></div><ArrowUpRight size={18} /></div></Reveal>)}</div>
      </section>

      <section className="difference-section" id="mvp">
        <div className="difference-main"><div className="section-label"><span>05</span><span>The first version</span></div><Reveal><h2>Not more content.<br /><em>More connection.</em></h2></Reveal><Reveal delay={0.1}><p>Thinkloop’s MVP is focused on one reliable promise: if you keep showing your thinking, it can keep helping you move forward.</p></Reveal><div className="mvp-list">{["Socratic tutoring that keeps the answer yours", "Topic-based assessments with reasoning evidence", "Likely misconception detection", "A persistent learner profile", "Progress and next-step recommendations"].map((item, index) => <Reveal key={item} delay={0.12 + index * 0.04}><div className="mvp-item"><span>0{index + 1}</span><p>{item}</p><Check size={16} /></div></Reveal>)}</div></div>
        <div className="closing-card"><div className="closing-ring ring-one" /><div className="closing-ring ring-two" /><div className="closing-mark"><span /><span /><span /></div><p>Keep the question.<br /><strong>Change the way<br />you find the answer.</strong></p><a href="/workspace" className="button button-light">Enter Workspace <ArrowUpRight size={16} /></a></div>
      </section>

      <footer className="site-footer">
        <a className="wordmark" href="#top" aria-label="Thinkloop home">
          <span className="wordmark-symbol" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="wordmark-text">thinkloop</span>
        </a>
        <p>Learning that leaves you with more than an answer.</p>
        <span className="footer-note">A cognitive learning system / 2025</span>
      </footer>
    </main>
  );
}
