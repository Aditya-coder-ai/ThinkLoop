"use client";

import React, { useEffect, useRef, useState, type FC, type ReactNode } from "react";
import { motion, useSpring } from "motion/react";

export type CursorVariant = "default" | "dot" | "custom";
export type SpringPreset = "default" | "snappy" | "floaty";

export interface SpringConfig {
  damping: number;
  stiffness: number;
  mass: number;
  restDelta?: number;
}

export const SPRING_PRESETS: Record<SpringPreset, SpringConfig> = {
  // Snappy: fast response with crisp damping
  snappy: { damping: 30, stiffness: 700, mass: 0.5, restDelta: 0.001 },
  // Default: balanced fluid motion
  default: { damping: 45, stiffness: 400, mass: 1, restDelta: 0.001 },
  // Floaty: looser, floaty drag effect
  floaty: { damping: 20, stiffness: 120, mass: 1.5, restDelta: 0.001 },
};

interface Position {
  x: number;
  y: number;
}

export interface SmoothCursorProps {
  /** Optional custom cursor element or icon */
  cursor?: ReactNode;
  /** Built-in appearance variant: "default" (Magic UI arrow), "dot" (mix-blend dot), or "custom" */
  variant?: CursorVariant;
  /** Spring physics preset: "default" | "snappy" | "floaty" */
  preset?: SpringPreset;
  /** Custom spring physics configuration (overrides preset if provided) */
  springConfig?: Partial<SpringConfig>;
  /** Optional extra CSS class on the cursor container */
  className?: string;
}

const DESKTOP_POINTER_QUERY = "(pointer: fine)";
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function isTrackablePointer(pointerType: string): boolean {
  return pointerType !== "touch";
}

/**
 * Default Magic UI smooth cursor SVG arrow with drop shadow
 */
const DefaultCursorSVG: FC = () => {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={42}
      height={46}
      viewBox="0 0 50 54"
      fill="none"
      className="drop-shadow-[0_2px_8px_rgba(0,0,0,0.35)]"
      style={{ transformOrigin: "top left" }}
    >
      <g filter="url(#smooth_cursor_filter)">
        <path
          d="M42.6817 41.1495L27.5103 6.79925C26.7269 5.02557 24.2082 5.02558 23.3927 6.79925L7.59814 41.1495C6.75833 42.9759 8.52712 44.8902 10.4125 44.1954L24.3757 39.0496C24.8829 38.8627 25.4385 38.8627 25.9422 39.0496L39.8121 44.1954C41.6849 44.8902 43.4884 42.9759 42.6817 41.1495Z"
          fill="#111827"
        />
        <path
          d="M43.7146 40.6933L28.5431 6.34306C27.3556 3.65428 23.5772 3.69516 22.3668 6.32755L6.57226 40.6778C5.3134 43.4156 7.97238 46.298 10.803 45.2549L24.7662 40.109C25.0221 40.0147 25.2999 40.0156 25.5494 40.1082L39.4193 45.254C42.2261 46.2953 44.9254 43.4347 43.7146 40.6933Z"
          stroke="#FFFFFF"
          strokeWidth={2.5}
        />
      </g>
      <defs>
        <filter
          id="smooth_cursor_filter"
          x={0.6}
          y={0.9}
          width={49}
          height={52.5}
          filterUnits="userSpaceOnUse"
          colorInterpolationFilters="sRGB"
        >
          <feFlood floodOpacity={0} result="BackgroundImageFix" />
          <feColorMatrix
            in="SourceAlpha"
            type="matrix"
            values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
            result="hardAlpha"
          />
          <feOffset dy={2} />
          <feGaussianBlur stdDeviation={2} />
          <feComposite in2="hardAlpha" operator="out" />
          <feColorMatrix
            type="matrix"
            values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.25 0"
          />
          <feBlend mode="normal" in2="BackgroundImageFix" result="effect1_dropShadow" />
          <feBlend mode="normal" in="SourceGraphic" in2="effect1_dropShadow" result="shape" />
        </filter>
      </defs>
    </svg>
  );
};

/**
 * Modern minimalist dot cursor with mix-blend-difference
 */
const DotCursor: FC = () => {
  return (
    <div
      className="h-4 w-4 rounded-full bg-white shadow-sm ring-1 ring-black/10"
      style={{
        mixBlendMode: "difference",
      }}
    />
  );
};

export function SmoothCursor({
  cursor,
  variant = "default",
  preset = "default",
  springConfig,
  className = "",
}: SmoothCursorProps) {
  const [isClient, setIsClient] = useState(false);
  const [isEnabled, setIsEnabled] = useState(false);
  const [isVisible, setIsVisible] = useState(false);

  const activeSpringConfig: SpringConfig = {
    ...SPRING_PRESETS[preset],
    ...(springConfig || {}),
  };

  const lastMousePos = useRef<Position>({ x: 0, y: 0 });
  const velocity = useRef<Position>({ x: 0, y: 0 });
  const lastUpdateTime = useRef(Date.now());
  const previousAngle = useRef(0);
  const accumulatedRotation = useRef(0);

  const cursorX = useSpring(0, activeSpringConfig);
  const cursorY = useSpring(0, activeSpringConfig);
  const rotation = useSpring(0, {
    ...activeSpringConfig,
    damping: Math.max(activeSpringConfig.damping * 1.3, 40),
    stiffness: Math.min(activeSpringConfig.stiffness * 0.75, 400),
  });
  const scale = useSpring(1, {
    ...activeSpringConfig,
    stiffness: 500,
    damping: 35,
  });

  // Client mounting & media query checks
  useEffect(() => {
    setIsClient(true);

    const pointerMedia = window.matchMedia(DESKTOP_POINTER_QUERY);
    const reducedMotionMedia = window.matchMedia(REDUCED_MOTION_QUERY);

    const checkEligibility = () => {
      // Must be desktop mouse (fine pointer) AND user must NOT prefer reduced motion
      const hasFinePointer = pointerMedia.matches;
      const prefersReducedMotion = reducedMotionMedia.matches;
      const eligible = hasFinePointer && !prefersReducedMotion;

      setIsEnabled(eligible);
      if (!eligible) {
        setIsVisible(false);
        document.documentElement.classList.remove("smooth-cursor-active");
      }
    };

    checkEligibility();

    pointerMedia.addEventListener("change", checkEligibility);
    reducedMotionMedia.addEventListener("change", checkEligibility);

    return () => {
      pointerMedia.removeEventListener("change", checkEligibility);
      reducedMotionMedia.removeEventListener("change", checkEligibility);
      document.documentElement.classList.remove("smooth-cursor-active");
    };
  }, []);

  // Pointer tracking & native cursor hiding
  useEffect(() => {
    if (!isEnabled) {
      return;
    }

    let scaleTimeout: ReturnType<typeof setTimeout> | null = null;
    let rafId = 0;

    const updateVelocity = (currentPos: Position) => {
      const currentTime = Date.now();
      const deltaTime = currentTime - lastUpdateTime.current;

      if (deltaTime > 0) {
        velocity.current = {
          x: (currentPos.x - lastMousePos.current.x) / deltaTime,
          y: (currentPos.y - lastMousePos.current.y) / deltaTime,
        };
      }

      lastUpdateTime.current = currentTime;
      lastMousePos.current = currentPos;
    };

    const handlePointerMove = (e: PointerEvent) => {
      if (!isTrackablePointer(e.pointerType)) {
        return;
      }

      // Hide native cursor everywhere and show smooth cursor
      document.documentElement.classList.add("smooth-cursor-active");
      setIsVisible(true);

      const currentPos = { x: e.clientX, y: e.clientY };
      updateVelocity(currentPos);

      const speed = Math.sqrt(
        Math.pow(velocity.current.x, 2) + Math.pow(velocity.current.y, 2)
      );

      cursorX.set(currentPos.x);
      cursorY.set(currentPos.y);

      // Rotate with mouse velocity if arrow variant
      if (variant === "default" && speed > 0.1) {
        const currentAngle =
          Math.atan2(velocity.current.y, velocity.current.x) * (180 / Math.PI) + 90;

        let angleDiff = currentAngle - previousAngle.current;
        if (angleDiff > 180) angleDiff -= 360;
        if (angleDiff < -180) angleDiff += 360;
        accumulatedRotation.current += angleDiff;
        rotation.set(accumulatedRotation.current);
        previousAngle.current = currentAngle;

        scale.set(0.95);

        if (scaleTimeout !== null) {
          clearTimeout(scaleTimeout);
        }

        scaleTimeout = setTimeout(() => {
          scale.set(1);
        }, 150);
      }
    };

    const handleThrottledPointerMove = (e: PointerEvent) => {
      if (!isTrackablePointer(e.pointerType)) {
        return;
      }

      if (rafId) return;

      rafId = requestAnimationFrame(() => {
        handlePointerMove(e);
        rafId = 0;
      });
    };

    const handlePointerLeave = () => {
      setIsVisible(false);
      document.documentElement.classList.remove("smooth-cursor-active");
    };

    const handlePointerEnter = () => {
      document.documentElement.classList.add("smooth-cursor-active");
      setIsVisible(true);
    };

    window.addEventListener("pointermove", handleThrottledPointerMove, { passive: true });
    document.addEventListener("mouseleave", handlePointerLeave);
    document.addEventListener("mouseenter", handlePointerEnter);

    return () => {
      window.removeEventListener("pointermove", handleThrottledPointerMove);
      document.removeEventListener("mouseleave", handlePointerLeave);
      document.removeEventListener("mouseenter", handlePointerEnter);
      document.documentElement.classList.remove("smooth-cursor-active");
      if (rafId) cancelAnimationFrame(rafId);
      if (scaleTimeout !== null) {
        clearTimeout(scaleTimeout);
      }
    };
  }, [cursorX, cursorY, rotation, scale, isEnabled, variant]);

  // SSR or non-eligible guard: render nothing and keep native cursor
  if (!isClient || !isEnabled) {
    return null;
  }

  const renderCursor = () => {
    if (cursor) return cursor;
    if (variant === "dot") return <DotCursor />;
    return <DefaultCursorSVG />;
  };

  return (
    <motion.div
      className={`smooth-cursor-container ${className}`}
      style={{
        position: "fixed",
        left: cursorX,
        top: cursorY,
        translateX: variant === "dot" ? "-50%" : "-15%",
        translateY: variant === "dot" ? "-50%" : "-15%",
        rotate: variant === "default" ? rotation : 0,
        scale: scale,
        zIndex: 999999,
        pointerEvents: "none",
        willChange: "transform",
        opacity: isVisible ? 1 : 0,
      }}
      initial={false}
      animate={{ opacity: isVisible ? 1 : 0 }}
      transition={{ duration: 0.15 }}
      aria-hidden="true"
    >
      {renderCursor()}
    </motion.div>
  );
}

export default SmoothCursor;
