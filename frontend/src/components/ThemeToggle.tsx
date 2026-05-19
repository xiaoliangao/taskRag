import { useThemeStore } from "../stores/themeStore";

export default function ThemeToggle() {
  const mode = useThemeStore((s) => s.mode);
  const toggle = useThemeStore((s) => s.toggle);

  return (
    <button
      type="button"
      className="mode-toggle"
      data-mode={mode}
      onClick={toggle}
      aria-label={mode === "night" ? "切换到日间模式" : "切换到夜间模式"}
      title={mode === "night" ? "切换到日间模式" : "切换到夜间模式"}
    >
      <span className="mode-toggle__track" aria-hidden />
      <span className="mode-toggle__cell mode-toggle__cell--n">N</span>
      <span className="mode-toggle__cell mode-toggle__cell--d">D</span>
    </button>
  );
}
