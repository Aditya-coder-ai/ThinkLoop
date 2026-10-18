import { ConceptItem, MisconceptionItem, BattleRound } from "./types";

export const CURRICULUM_CONCEPTS: ConceptItem[] = [
  {
    id: "vectors_in_physics",
    title: "Vectors in Physics",
    domain: "physics",
    topic: "mechanics",
    description:
      "Vectors possess both magnitude and direction, providing the essential mathematical foundation for kinematics and dynamics.",
    difficulty: 1,
    prerequisites: [],
  },
  {
    id: "displacement_and_velocity",
    title: "Displacement and Velocity",
    domain: "physics",
    topic: "mechanics",
    description:
      "Position, displacement, speed, and velocity describe how an object's location changes continuously over time.",
    difficulty: 1,
    prerequisites: ["vectors_in_physics"],
  },
  {
    id: "acceleration",
    title: "Acceleration",
    domain: "physics",
    topic: "mechanics",
    description:
      "Acceleration quantifies the rate of change of velocity with respect to time, including speeding up, slowing down, or turning.",
    difficulty: 2,
    prerequisites: ["displacement_and_velocity"],
  },
  {
    id: "free_body_diagrams",
    title: "Free-Body Diagrams",
    domain: "physics",
    topic: "mechanics",
    description:
      "Visual representations that isolate a system and display all external contact and field forces with vector arrows.",
    difficulty: 2,
    prerequisites: ["vectors_in_physics"],
  },
  {
    id: "newtons_first_law",
    title: "Newton's First Law (Inertia)",
    domain: "physics",
    topic: "mechanics",
    description:
      "An object maintains a constant state of rest or uniform straight-line motion unless acted upon by a net external force.",
    difficulty: 2,
    prerequisites: ["acceleration", "free_body_diagrams"],
  },
  {
    id: "newtons_second_law",
    title: "Newton's Second Law",
    domain: "physics",
    topic: "mechanics",
    description:
      "The net external force on an object equals the product of its mass and acceleration vector: F_net = m * a.",
    difficulty: 2,
    prerequisites: ["newtons_first_law"],
  },
  {
    id: "newtons_third_law",
    title: "Newton's Third Law (Action-Reaction)",
    domain: "physics",
    topic: "mechanics",
    description:
      "Forces always occur in matched pairs: equal in magnitude, opposite in direction, acting on different bodies simultaneously.",
    difficulty: 2,
    prerequisites: ["newtons_second_law"],
  },
  {
    id: "weight_and_normal_force",
    title: "Weight and Normal Force",
    domain: "physics",
    topic: "mechanics",
    description:
      "Weight is the downward gravitational pull, while the normal force is the perpendicular contact support from a surface.",
    difficulty: 2,
    prerequisites: ["newtons_third_law"],
  },
  {
    id: "friction_static_and_kinetic",
    title: "Friction: Static & Kinetic",
    domain: "physics",
    topic: "mechanics",
    description:
      "Frictional forces resist impending relative motion (static) or active sliding motion (kinetic) along contact interfaces.",
    difficulty: 3,
    prerequisites: ["weight_and_normal_force"],
  },
  {
    id: "conservation_of_momentum",
    title: "Conservation of Momentum",
    domain: "physics",
    topic: "mechanics",
    description:
      "The total linear momentum of an isolated system remains constant in the absence of net external impulse.",
    difficulty: 3,
    prerequisites: ["newtons_third_law"],
  },
];

export const CURRICULUM_MISCONCEPTIONS: MisconceptionItem[] = [
  {
    id: "misc_motion_requires_force",
    conceptId: "newtons_first_law",
    statement: "An object needs a continuous forward force acting on it to keep moving at a constant speed.",
    correctIdea:
      "By Newton's first law, an object in motion continues with constant velocity unless a net external force opposes it.",
    conflictPrompt:
      "Predict what will happen to a spacecraft drifting in deep space after its engines are completely turned off.",
  },
  {
    id: "misc_acceleration_same_as_velocity",
    conceptId: "acceleration",
    statement: "Velocity and acceleration are basically the same thing, so zero velocity means zero acceleration.",
    correctIdea:
      "Velocity is the rate of position change; acceleration is the rate of velocity change. A turning ball can momentarily have zero velocity while under non-zero acceleration.",
    conflictPrompt:
      "Predict the acceleration of a ball thrown straight upward at the exact instant it reaches its peak height.",
  },
  {
    id: "misc_fbd_includes_internal_forces",
    conceptId: "free_body_diagrams",
    statement: "A free-body diagram should show the forces that the object exerts on its surroundings.",
    correctIdea:
      "A free-body diagram strictly isolates the system and displays only external forces acting ON the object.",
    conflictPrompt:
      "Predict whether a book's downward push on a table should be drawn on the free-body diagram of the book.",
  },
  {
    id: "misc_heavier_objects_fall_faster",
    conceptId: "weight_and_normal_force",
    statement: "Heavier objects fall significantly faster in free fall because Earth pulls on them with more force.",
    correctIdea:
      "While gravitational force is proportional to mass (F = mg), inertial resistance is also proportional to mass (a = F/m = g), so acceleration is identical for all masses in vacuum.",
    conflictPrompt:
      "If a 10 kg bowling ball and a 0.1 kg baseball are dropped simultaneously in a vacuum chamber, which hits the ground first?",
  },
  {
    id: "misc_normal_force_equals_weight_always",
    conceptId: "weight_and_normal_force",
    statement: "Normal force is always equal and opposite to the gravitational weight of an object.",
    correctIdea:
      "Normal force adjusts based on perpendicular contact constraints (e.g. on an inclined ramp, N = m * g * cos(theta)).",
    conflictPrompt:
      "What happens to the normal force on a box as you place it on a steep 45-degree ramp?",
  },
];

export const SAMPLE_BATTLE_PROBLEMS: BattleRound[] = [
  {
    index: 1,
    problemId: "p_accel_1",
    prompt: "A sports car accelerates uniformly from rest to 30 m/s in 6 seconds. Calculate its acceleration.",
    expectedAnswer: "5",
    unit: "m/s²",
    timeLimitSeconds: 25,
  },
  {
    index: 2,
    problemId: "p_newton2_1",
    prompt: "A constant net horizontal force of 40 N is applied to an 8 kg sled on frictionless ice. What is the sled's acceleration?",
    expectedAnswer: "5",
    unit: "m/s²",
    timeLimitSeconds: 20,
  },
  {
    index: 3,
    problemId: "p_fbd_1",
    prompt: "A 2 kg book rests motionless on a horizontal desk. If g = 9.8 m/s², what is the magnitude of the normal force exerted by the desk on the book?",
    expectedAnswer: "19.6",
    unit: "N",
    timeLimitSeconds: 25,
  },
];

export const STRATEGY_EXPLANATIONS: Record<string, { label: string; explanation: string }> = {
  guided_hint: {
    label: "Guided Hint",
    explanation: "Learner has intermediate mastery; offering a targeted nudge without giving away the solution.",
  },
  cognitive_conflict: {
    label: "Cognitive Conflict",
    explanation: "A common misconception was identified; presenting a counter-example to challenge the mental model.",
  },
  worked_example: {
    label: "Worked Example",
    explanation: "Mastery is low or concept is new; walking through a concrete model step-by-step.",
  },
  socratic_challenge: {
    label: "Socratic Challenge",
    explanation: "Mastery is high (>= 70%); prompting the learner to generalize or connect to higher-order principles.",
  },
  prerequisite_review: {
    label: "Prerequisite Review",
    explanation: "A foundational concept is shaky; pausing to reinforce the necessary prerequisite.",
  },
};
