/** A deliberately small, safe renderer for the Markdown returned by the health-analysis API. */
function InlineMarkdown({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('*') && part.endsWith('*')) return <em key={index}>{part.slice(1, -1)}</em>;
    return part;
  });
}

export default function MarkdownContent({ content }) {
  const lines = String(content || '').split(/\r?\n/);
  const output = [];
  let listItems = [];
  let listType = null;
  const flushList = () => {
    if (!listItems.length) return;
    const List = listType === 'ordered' ? 'ol' : 'ul';
    output.push(<List key={`list-${output.length}`} className={listType === 'ordered' ? 'my-3 list-decimal space-y-1 pl-5' : 'my-3 list-disc space-y-1 pl-5'}>{listItems}</List>);
    listItems = [];
    listType = null;
  };
  lines.forEach((line, index) => {
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    const bullet = line.match(/^[-*]\s+(.+)$/);
    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (bullet || ordered) {
      const nextType = ordered ? 'ordered' : 'bullet';
      if (listType && listType !== nextType) flushList();
      listType = nextType;
      listItems.push(<li key={index}><InlineMarkdown text={(bullet || ordered)[1]} /></li>);
      return;
    }
    flushList();
    if (heading) {
      const Tag = `h${heading[1].length}`;
      output.push(<Tag key={index} className="mt-4 mb-2 font-semibold text-slate-900 first:mt-0 dark:text-white"><InlineMarkdown text={heading[2]} /></Tag>);
    } else if (line.trim()) {
      output.push(<p key={index} className="mb-2 leading-6"><InlineMarkdown text={line} /></p>);
    }
  });
  flushList();
  return <div>{output}</div>;
}
