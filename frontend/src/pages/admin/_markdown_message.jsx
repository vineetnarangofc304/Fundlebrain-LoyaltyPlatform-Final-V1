import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/** Download a Fundle-Brain CSV export through the authenticated api client. */
const downloadExport = async (href) => {
  try {
    // Normalise absolute/relative hrefs to an api-relative path (strip .../api)
    const path = href.replace(/^https?:\/\/[^/]+/, "").replace(/^\/api/, "");
    const r = await api.get(path, { responseType: "blob" });
    const ctype = r.headers["content-type"] || "";
    if (r.status === 202 || ctype.includes("application/json")) {
      toast.info("Export is still being prepared — try again in a few seconds.");
      return;
    }
    const cd = r.headers["content-disposition"] || "";
    const m = cd.match(/filename="?([^";]+)/);
    const name = m ? m[1] : "export.csv";
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Downloading ${name}`);
  } catch (e) {
    if (e?.response?.status === 202) {
      toast.info("Export is still being prepared — try again in a few seconds.");
    } else {
      toast.error(e?.response?.data?.detail || "Download failed");
    }
  }
};

const components = {
  h1: ({ children }) => <h3 className="font-display text-lg font-semibold mt-3 mb-1.5">{children}</h3>,
  h2: ({ children }) => <h3 className="font-display text-base font-semibold mt-3 mb-1.5">{children}</h3>,
  h3: ({ children }) => <h4 className="text-sm font-semibold uppercase tracking-wide mt-3 mb-1.5 kazo-text-burgundy">{children}</h4>,
  p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold kazo-text-burgundy">{children}</strong>,
  ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  code: ({ children }) => (
    <code className="px-1 py-0.5 bg-neutral-100 border border-black/10 text-[12px] font-mono">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="p-3 bg-neutral-900 text-neutral-100 text-[12px] font-mono overflow-x-auto mb-2 [&_code]:bg-transparent [&_code]:border-0 [&_code]:p-0 [&_code]:text-neutral-100">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto mb-3 border border-black/10">
      <table className="w-full text-[13px] border-collapse" data-testid="ai-markdown-table">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-neutral-50">{children}</thead>,
  th: ({ children }) => (
    <th className="text-left px-3 py-2 border-b border-black/10 text-[10px] uppercase tracking-widest text-neutral-500 whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="px-3 py-1.5 border-b border-black/5 align-top">{children}</td>,
  hr: () => <hr className="my-3 border-black/10" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-[var(--kazo-burgundy)] pl-3 my-2 text-neutral-600 italic">{children}</blockquote>
  ),
  a: ({ href, children }) => {
    if (href && href.includes("/ai/exports/")) {
      return (
        <button
          type="button"
          onClick={() => downloadExport(href)}
          data-testid="ai-csv-download-btn"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 my-1 kazo-bg-burgundy text-white text-xs font-medium hover:opacity-90 transition-opacity"
        >
          <Download className="w-3.5 h-3.5" /> {children}
        </button>
      );
    }
    return (
      <a href={href} target="_blank" rel="noreferrer" className="underline kazo-text-burgundy">
        {children}
      </a>
    );
  },
};

/** Renders Fundle Brain assistant replies as rich GFM markdown (tables, bold,
 * bullets) with CSV-export links wired to authenticated downloads. */
export default function MarkdownMessage({ content }) {
  return (
    <div className="ai-markdown" data-testid="ai-markdown-message">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content || ""}
      </ReactMarkdown>
    </div>
  );
}
