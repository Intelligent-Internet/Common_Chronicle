import type { TimelineEvent, BackendTaskRecord, EventSourceInfo } from '../types';
import { getStartDateISO, getEndDateISO } from '../types';

function triggerDownload(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  // Clean up the URL object
  URL.revokeObjectURL(url);
}

export function exportEventsAsJson(
  task: BackendTaskRecord,
  events: TimelineEvent[],
  sources: Record<string, EventSourceInfo>
): void {
  const exportData = {
    taskInfo: {
      id: task.id,
      topic: task.topic_text,
      status: task.status,
      createdAt: task.created_at,
      dataSourcePreference: task.config?.data_source_preference || 'default',
    },
    exportedAt: new Date().toISOString(),
    eventsCount: events.length,
    sourcesCount: Object.keys(sources).length,
    sources: sources,
    events: events,
  };

  const jsonContent = JSON.stringify(exportData, null, 2);
  const filename = `timeline-${task.id}.json`;

  triggerDownload(jsonContent, filename, 'application/json');
}

export function exportEventsAsMarkdown(
  task: BackendTaskRecord,
  events: TimelineEvent[],
  sources: Record<string, EventSourceInfo>
): void {
  let markdownContent = `# Timeline for: ${task.topic_text}\n\n`;
  markdownContent += `**Task ID:** ${task.id}\n`;
  markdownContent += `**Generated at:** ${new Date().toLocaleString()}\n`;
  markdownContent += `**Events Count:** ${events.length}\n`;
  markdownContent += `**Data Sources:** ${task.config?.data_source_preference || 'Default'}\n\n`;
  markdownContent += `---\n\n`;

  if (!events || events.length === 0) {
    markdownContent += 'No events were found for this timeline.\n\n';
    markdownContent += `---\n\n`;
  } else {
    events.forEach((event, index) => {
      // Use description as the title if available, or use a default title
      const eventTitle = event.description || `Event ${index + 1}`;
      markdownContent += `## ${index + 1}. ${eventTitle}\n\n`;

      if (event.event_date_str) {
        markdownContent += `**Date:** ${event.event_date_str}\n\n`;
      }

      // Add date range if available
      if (event.date_info) {
        const startDate = getStartDateISO(event.date_info);
        const endDate = getEndDateISO(event.date_info);
        if (startDate && endDate && startDate !== endDate) {
          markdownContent += `**Date Range:** ${startDate} to ${endDate}\n\n`;
        }
      }

      if (event.source_snippets && Object.keys(event.source_snippets).length > 0) {
        const representativeSnippet = Object.values(event.source_snippets)[0];
        if (representativeSnippet) {
          markdownContent += `**Representative Source Snippet:** ${representativeSnippet}\n\n`;
        }
      }

      // Add sources if available - resolve source references
      const eventSources = Object.keys(event.source_snippets)
        .map((ref) => sources[ref])
        .filter(Boolean);
      if (eventSources.length > 0) {
        markdownContent += `### Sources:\n\n`;
        eventSources.forEach((source) => {
          if (source.source_url) {
            markdownContent += `- [${source.source_page_title || 'Source'}](${source.source_url})\n`;
          } else {
            markdownContent += `- ${source.source_page_title || 'Source'}\n`;
          }
        });
        markdownContent += `\n`;
      }

      // Add entities if available
      if (event.main_entities && event.main_entities.length > 0) {
        markdownContent += `### Related Entities:\n\n`;
        event.main_entities.forEach((entity) => {
          markdownContent += `- **${entity.original_name}** (${entity.entity_type})`;
          markdownContent += `\n`;
        });
        markdownContent += `\n`;
      }

      markdownContent += `---\n\n`;
    });
  }

  // Add footer
  markdownContent += `\n*Exported from Common Chronicle on ${new Date().toLocaleString()}*\n`;

  const filename = `timeline-${task.id}.md`;
  triggerDownload(markdownContent, filename, 'text/markdown');
}
