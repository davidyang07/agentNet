import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Crosshair,
  History,
  Info,
  Layers,
  Pause,
  Play,
  RotateCcw,
  Search,
  ShieldCheck,
  ShieldHalf,
  TriangleAlert,
  Wrench,
  X,
  type LucideIcon,
  type LucideProps,
} from "lucide-react";

// The product's icons, by role. Every glyph is lucide-react — the one icon set
// (DESIGN.md › Iconography) — at 16px with a 1.75 stroke; a call site sizes it
// with a `size-*` class and colours it through `currentColor`.

function role(Glyph: LucideIcon) {
  function RoleIcon(props: LucideProps) {
    return <Glyph size={16} strokeWidth={1.75} aria-hidden {...props} />;
  }
  RoleIcon.displayName = Glyph.displayName;
  return RoleIcon;
}

export const IconShieldCheck = role(ShieldCheck);
export const IconWrench = role(Wrench);
export const IconHistory = role(History);
export const IconPlay = role(Play);
export const IconPause = role(Pause);
export const IconRestart = role(RotateCcw);
export const IconClose = role(X);
export const IconChevronRight = role(ChevronRight);
export const IconChevronDown = role(ChevronDown);
export const IconArrowLeft = role(ArrowLeft);
export const IconArrowRight = role(ArrowRight);
export const IconSearch = role(Search);
export const IconTarget = role(Crosshair);
export const IconLayers = role(Layers);
export const IconAlert = role(TriangleAlert);
export const IconInfo = role(Info);

/** The product mark: a half-filled shield. */
export const BrandMark = role(ShieldHalf);
