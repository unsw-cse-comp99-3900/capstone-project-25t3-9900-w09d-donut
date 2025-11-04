import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import { readSummaryReviewSnapshot, writeSummaryReviewSnapshot } from '../services/summaryReviewState';

const API_BASE_URL = (process.env.REACT_APP_API_BASE_URL || '').replace(/\/$/, '');

const sanitizeAscii = (value = '') => value.replace(/[^\x09\x0A\x0D\x20-\x7E]/g, '?');

const normalizePdfUrl = (rawUrl) => {
  if (!rawUrl) {
    return null;
  }
  const trimmed = String(rawUrl).trim();

  // Already a relative URL or data URL.
  if (/^(\.|\/)/.test(trimmed) || /^data:/i.test(trimmed)) {
    return trimmed;
  }

  try {
    const parsed = new URL(trimmed, window.location.origin);
    const backendHostPattern = /(^|\.)backend$/i;

    if (backendHostPattern.test(parsed.hostname)) {
      const path = parsed.pathname.startsWith('/') ? parsed.pathname : `/${parsed.pathname}`;
      return `${path}${parsed.search || ''}`;
    }

    if (API_BASE_URL) {
      try {
        const apiOrigin = new URL(API_BASE_URL, window.location.origin).origin;
        if (parsed.origin === apiOrigin) {
          return parsed.toString();
        }
      } catch (err) {
        // ignore parse issues, fall through to default return
      }
    }

    return parsed.toString();
  } catch (err) {
    console.warn('Unable to normalize PDF URL', err);
    return trimmed;
  }
};

const parseFilenameFromContentDisposition = (header) => {
  if (!header) {
    return null;
  }
  const filenameMatch = header.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  if (filenameMatch) {
    const encoded = filenameMatch[1] || filenameMatch[2];
    try {
      return decodeURIComponent(encoded);
    } catch (err) {
      return encoded;
    }
  }
  return null;
};

const formatTimestamp = (value) => {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

const escapePdfText = (value) => {
  if (!value) {
    return '';
  }
  return String(value).replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)').replace(/\r?\n/g, '\\n');
};

const normalizeTimestamp = (value) => {
  if (!value) {
    return 0;
  }
  const date = new Date(value);
  const time = date.getTime();
  return Number.isNaN(time) ? 0 : time;
};

const sortSummaryRecords = (items) => {
  if (!Array.isArray(items)) {
    return [];
  }
  return [...items].sort((a, b) => {
    const aTime = normalizeTimestamp(a?.updated_at || a?.created_at);
    const bTime = normalizeTimestamp(b?.updated_at || b?.created_at);
    return bTime - aTime;
  });
};

const splitIntoLines = (text, width = 90) => {
  if (!text) {
    return [''];
  }
  const lines = [];
  const sanitized = sanitizeAscii(text);
  sanitized.split(/\r?\n/).forEach((segment) => {
    const trimmed = segment.trimEnd();
    if (!trimmed.length) {
      lines.push('');
      return;
    }
    let remaining = trimmed;
    while (remaining.length > width) {
      let splitIndex = remaining.lastIndexOf(' ', width);
      if (splitIndex <= 0) {
        splitIndex = width;
      }
      lines.push(remaining.slice(0, splitIndex).trimEnd());
      remaining = remaining.slice(splitIndex).replace(/^\s+/, '');
    }
    if (remaining.length) {
      lines.push(remaining);
    }
  });
  if (!lines.length) {
    lines.push('');
  }
  return lines;
};

const wrapParagraphs = (text, width = 90) => splitIntoLines(text, width);

const downloadPdfFromUrl = async (pdfUrl, fallbackFilename, email) => {
  const finalUrl = normalizePdfUrl(pdfUrl);
  if (!finalUrl) {
    throw new Error('Missing PDF URL');
  }
  const response = await axios.get(finalUrl, {
    responseType: 'blob',
    headers: email ? { 'X-User-Email': email } : undefined,
  });
  const blob = response.data;
  const contentDisposition = response.headers?.['content-disposition'];
  const filename = parseFilenameFromContentDisposition(contentDisposition) || fallbackFilename || 'summary.pdf';
  const blobUrl = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = blobUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  } finally {
    URL.revokeObjectURL(blobUrl);
  }
};

const buildContentStream = (lines) => {
  const commands = ['BT', '/F1 12 Tf'];
  let y = 760;
  const lineHeight = 14;
  lines.forEach((line) => {
    commands.push(`1 0 0 1 50 ${y} Tm (${escapePdfText(line)}) Tj`);
    y -= lineHeight;
    if (y < 60) {
      y = 760;
    }
  });
  commands.push('ET');
  return `${commands.join('\n')}\n`;
};

const composePdf = (stream) => {
  const encoder = new TextEncoder();
  const objects = [];
  const addObject = (obj) => {
    objects.push(obj.endsWith('\n') ? obj : `${obj}\n`);
  };

  addObject('1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj');
  addObject('2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj');
  addObject(
    '3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj'
  );
  addObject('4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj');

  const streamBytes = encoder.encode(stream);
  addObject(`5 0 obj << /Length ${streamBytes.length} >> stream\n${stream}endstream endobj`);

  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  let cursor = pdf.length;
  objects.forEach((obj) => {
    offsets.push(cursor);
    pdf += obj;
    cursor += obj.length;
  });

  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n`;
  pdf += '0000000000 65535 f \n';
  for (let index = 1; index < offsets.length; index += 1) {
    pdf += `${offsets[index].toString().padStart(10, '0')} 00000 n \n`;
  }
  pdf += 'trailer\n';
  pdf += `<< /Size ${objects.length + 1} /Root 1 0 R >>\n`;
  pdf += `startxref\n${xrefOffset}\n%%EOF`;

  return encoder.encode(pdf);
};

const createFallbackPdfBlob = ({ summaryText, citations, focusAspect }) => {
  const lines = [];
  lines.push(focusAspect ? `Summary - Focus: ${sanitizeAscii(focusAspect)}` : 'Summary');
  lines.push('');

  wrapParagraphs(summaryText).forEach((line) => lines.push(line));

  const citationList = Array.isArray(citations) ? citations.filter(Boolean) : [];
  if (citationList.length) {
    lines.push('');
    lines.push('References:');
    citationList.forEach((item, idx) => {
      wrapParagraphs(`${idx + 1}. ${item}`).forEach((line) => lines.push(line));
    });
  }

  const contentStream = buildContentStream(lines);
  const pdfBytes = composePdf(contentStream);
  return new Blob([pdfBytes], { type: 'application/pdf' });
};

const buildFallbackFilename = (sessionId, summaryType, focusAspect) => {
  const pieces = ['summary'];
  if (sessionId) {
    pieces.push(sessionId);
  }
  if (summaryType) {
    pieces.push(summaryType);
  }
  if (focusAspect) {
    pieces.push(focusAspect.replace(/\s+/g, '_').slice(0, 40));
  }
  const joined = pieces.join('_').replace(/[^A-Za-z0-9_\-]/g, '_');
  return `${joined || 'summary_export'}.pdf`;
};

const roleLabel = {
  user: 'You',
  assistant: 'AI',
};

const SummaryReviewPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = location.state;
  const persistedSnapshot = useMemo(() => readSummaryReviewSnapshot(), []);
  const state = locationState ?? persistedSnapshot ?? {};

  const initialAssistantData = (() => {
    if (Array.isArray(state?.messages) && state.messages.length) {
      const lastAssistant = [...state.messages].reverse().find((msg) => msg.role === 'assistant');
      if (lastAssistant) {
        const citations = Array.isArray(lastAssistant.metadata?.citations) ? lastAssistant.metadata.citations : [];
        const metadata = lastAssistant.metadata?.metadata || state?.summaryMetadata || null;
        return { citations, metadata };
      }
    }
    const metadata = state?.summaryMetadata || null;
    const citations = Array.isArray(state?.summaryCitations)
      ? state.summaryCitations
      : Array.isArray(state?.summaryMetadata?.citations)
      ? state.summaryMetadata.citations
      : Array.isArray(state?.citations)
      ? state.citations
      : [];
    return { citations, metadata };
  })();

  const initialSummaryHistory = Array.isArray(state?.summaryHistory)
    ? sortSummaryRecords(
        state.summaryHistory.map((item) => ({
          ...item,
          pdf_url: normalizePdfUrl(item.pdf_url),
        }))
      )
    : [];
  const initialActiveSummaryId = state?.activeSummaryId ?? initialSummaryHistory[0]?.id ?? state?.summaryId ?? null;

  const [summary, setSummary] = useState(state?.summaryText || '');
  const [historyId] = useState(state?.historyId ?? null);
  const [sessionId, setSessionId] = useState(state?.sessionId ?? null);
  const [initialPlan] = useState(state?.initialPlan || '');
  const [summaryPdfUrl, setSummaryPdfUrl] = useState(() => normalizePdfUrl(state?.summaryPdfUrl));
  const [summaryId, setSummaryId] = useState(state?.summaryId || null);
  const [summaryHistory, setSummaryHistory] = useState(initialSummaryHistory);
  const [activeSummaryId, setActiveSummaryId] = useState(initialActiveSummaryId);
  const [summaryMetadata, setSummaryMetadata] = useState(initialAssistantData.metadata || null);
  const [summaryCitations, setSummaryCitations] = useState(initialAssistantData.citations || []);
  const [messages, setMessages] = useState(() => {
    if (Array.isArray(state?.messages) && state.messages.length) {
      return state.messages.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        metadata: m.metadata,
      }));
    }
    if (state?.summaryText) {
      return [{ role: 'assistant', content: state.summaryText }];
    }
    return [];
  });
  const [input, setInput] = useState('');
  const [initializing, setInitializing] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const fallbackObjectUrlRef = useRef(null);

  const authEmail = useMemo(() => localStorage.getItem('authEmail') || null, []);

  const applySummaryRecord = useCallback((record, options = {}) => {
    if (!record) {
      return;
    }
    setSummary(record.summary_text || '');
    setSummaryPdfUrl(normalizePdfUrl(record.pdf_url));
    setSummaryId(record.id || null);
    setActiveSummaryId(record.id || null);
    setSummaryMetadata((prev) => {
      const next = options.preserveMetadata && prev ? { ...prev } : {};
      if (record.metadata && typeof record.metadata === 'object') {
        Object.entries(record.metadata).forEach(([key, value]) => {
          if (value !== undefined) {
            next[key] = value;
          }
        });
      }
      if (record.summary_type) {
        next.summary_type = record.summary_type;
      } else if (!options.preserveMetadata) {
        delete next.summary_type;
      }
      if (record.focus_aspect) {
        next.focus_aspect = record.focus_aspect;
      } else if (!options.preserveMetadata) {
        delete next.focus_aspect;
      }
      return Object.keys(next).length ? next : null;
    });
    if (Array.isArray(record.citations)) {
      setSummaryCitations(record.citations);
    } else if (!options.preserveCitations) {
      setSummaryCitations([]);
    }
  }, []);

  const loadSummaryHistory = useCallback(
    async (targetSessionId, options = {}) => {
      if (!targetSessionId) {
        return;
      }
      try {
        const headers = authEmail ? { 'X-User-Email': authEmail } : undefined;
        const response = await axios.get(
          `${API_BASE_URL}/api/chat/sessions/${targetSessionId}/summaries`,
          { headers }
        );
        const list = Array.isArray(response.data?.summaries)
          ? sortSummaryRecords(
              response.data.summaries.map((item) => ({
                ...item,
                pdf_url: normalizePdfUrl(item.pdf_url),
              }))
            )
          : [];
        setSummaryHistory(list);
        if (!list.length) {
          return list;
        }
        const preferred =
          (options.preferSummaryId && list.find((item) => item.id === options.preferSummaryId)) ||
          (activeSummaryId && list.find((item) => item.id === activeSummaryId)) ||
          list[0];
        if (preferred) {
          applySummaryRecord(preferred, {
            preserveCitations: options.preserveCitations,
            preserveMetadata: options.preserveMetadata,
          });
        }
        return list;
      } catch (err) {
        console.warn('Unable to load session summaries', err);
        return null;
      }
    },
    [authEmail, activeSummaryId, applySummaryRecord]
  );

  const ensureSession = useCallback(
    async ({ reload = false } = {}) => {
      if (!authEmail || !historyId) {
        return null;
      }

      const headers = authEmail ? { 'X-User-Email': authEmail } : undefined;

      const applyMessages = (items) => {
        const normalized = Array.isArray(items)
          ? items.map((item) => ({
              id: item.id,
              role: item.role,
              content: item.content,
              metadata: item.metadata,
            }))
          : [];
        setMessages(normalized);
        const lastAssistant = [...normalized].reverse().find((msg) => msg.role === 'assistant');
        if (lastAssistant?.content) {
          setSummary(lastAssistant.content);
        }
        if (lastAssistant?.metadata) {
          if (Array.isArray(lastAssistant.metadata.citations)) {
            setSummaryCitations(lastAssistant.metadata.citations);
          }
          if (lastAssistant.metadata.metadata) {
            setSummaryMetadata(lastAssistant.metadata.metadata);
          }
        }
      };

      let resolvedSessionId = sessionId || null;

      if (!resolvedSessionId) {
        setInitializing(true);
        setError('');
        try {
          const response = await axios.post(
            `${API_BASE_URL}/api/chat/sessions`,
            { history_id: historyId, user_email: authEmail },
            { headers }
          );
          const data = response.data || {};
          resolvedSessionId = data.session_id || null;
          if (resolvedSessionId && resolvedSessionId !== sessionId) {
            setSessionId(resolvedSessionId);
          }
          applyMessages(data.messages);
          if (resolvedSessionId) {
            await loadSummaryHistory(resolvedSessionId, {
              preserveCitations: true,
              preserveMetadata: true,
            });
          }
          return resolvedSessionId;
        } catch (err) {
          const message = err.response?.data?.error || err.message || 'Unable to initialize the refinement chat.';
          setError(message);
          return null;
        } finally {
          setInitializing(false);
        }
      }

      if (!reload) {
        return resolvedSessionId;
      }

      setInitializing(true);
      setError('');
      try {
        const response = await axios.get(`${API_BASE_URL}/api/chat/sessions/${resolvedSessionId}`, { headers });
        const data = response.data || {};
        applyMessages(data.messages);
        await loadSummaryHistory(resolvedSessionId, {
          preserveCitations: true,
          preserveMetadata: true,
        });
        return resolvedSessionId;
      } catch (err) {
        const message = err.response?.data?.error || err.message || 'Unable to initialize the refinement chat.';
        setError(message);
        return null;
      } finally {
        setInitializing(false);
      }
    },
    [authEmail, historyId, sessionId, loadSummaryHistory]
  );

  useEffect(() => {
    if (!historyId || !authEmail) {
      return;
    }
    ensureSession({ reload: true });
  }, [authEmail, historyId, ensureSession]);

  useEffect(() => {
    if (!summaryHistory.length || !activeSummaryId) {
      return;
    }
    if (summaryId === activeSummaryId) {
      return;
    }
    const match = summaryHistory.find((item) => item.id === activeSummaryId);
    if (match) {
      applySummaryRecord(match, { preserveCitations: true, preserveMetadata: true });
    }
  }, [summaryHistory, activeSummaryId, summaryId, applySummaryRecord]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed) {
      return;
    }
    if (!authEmail) {
      setError('Sign in to chat with the AI.');
      return;
    }

    let activeSessionId = sessionId;
    if (!activeSessionId) {
      activeSessionId = await ensureSession();
    }
    if (!activeSessionId) {
      setError('Unable to reach the AI session. Please make sure you are signed in.');
      return;
    }

    const clientMessageId = `pending-${Date.now()}`;
    const userMessage = { id: clientMessageId, role: 'user', content: trimmed };
    const assistantPlaceholder = { id: `${clientMessageId}-assistant`, role: 'assistant', content: '', pending: true };

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
    setInput('');

    setSending(true);
    setError('');
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/chat/sessions/${activeSessionId}/messages`,
        { message: trimmed, history_id: historyId, user_email: authEmail },
        { headers: { 'X-User-Email': authEmail } }
      );
      const data = response.data || {};
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id === clientMessageId) {
            return msg;
          }
          if (msg.id === assistantPlaceholder.id) {
            return {
              id: assistantPlaceholder.id,
              role: 'assistant',
              content: data.reply || 'The assistant did not return a response.',
              metadata: data.metadata,
            };
          }
          return msg;
        })
      );
      if (data.reply) {
        setSummary(data.reply);
      }
      if (data.pdf_url) {
        setSummaryPdfUrl(normalizePdfUrl(data.pdf_url));
      }
      if (data.summary_id) {
        setSummaryId(data.summary_id);
      }
      if (data.metadata) {
        setSummaryMetadata(data.metadata);
      }
      if (Array.isArray(data.citations)) {
        setSummaryCitations(data.citations);
      }
      await loadSummaryHistory(activeSessionId, {
        preferSummaryId: data.summary_id,
        preserveCitations: true,
        preserveMetadata: true,
      });
    } catch (err) {
      const message = err.response?.data?.error || err.message || 'We could not deliver your request. Try again in a moment.';
      setError(message);
      setMessages((prev) => prev.filter((msg) => msg.id !== assistantPlaceholder.id));
    } finally {
      setSending(false);
    }
  };

  const handleDownloadClick = useCallback(async () => {
    const focusAspect = summaryMetadata?.focus_aspect || summaryMetadata?.focusAspect || null;
    const summaryType = summaryMetadata?.summary_type || summaryMetadata?.summaryType || 'manual';
    const fallbackFilename = buildFallbackFilename(sessionId || 'current', summaryType, focusAspect || undefined);

    if (summaryPdfUrl) {
      try {
        await downloadPdfFromUrl(summaryPdfUrl, fallbackFilename, authEmail);
        return;
      } catch (remoteErr) {
        console.warn('Falling back to client-side PDF generation due to download error', remoteErr);
      }
    }

    try {
      const summaryText = (summary && summary.trim()) || (initialPlan && initialPlan.trim()) || 'Summary is not available yet.';
      const blob = createFallbackPdfBlob({
        summaryText,
        citations: summaryCitations,
        focusAspect,
      });
      if (fallbackObjectUrlRef.current) {
        URL.revokeObjectURL(fallbackObjectUrlRef.current);
      }
      const objectUrl = URL.createObjectURL(blob);
      fallbackObjectUrlRef.current = objectUrl;
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = fallbackFilename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (downloadErr) {
      console.error('Failed to download summary PDF fallback', downloadErr);
    }
  }, [summaryPdfUrl, summary, initialPlan, summaryMetadata, summaryCitations, sessionId, authEmail]);

  const handleHistorySelect = useCallback(
    (record) => {
      if (!record) {
        return;
      }
      applySummaryRecord(record);
    },
    [applySummaryRecord]
  );

  const handleHistoryDownload = useCallback(
    async (record) => {
      if (!record) {
        return;
      }
      const focusValue =
        record.focus_aspect ||
        record.metadata?.focus_aspect ||
        record.metadata?.focusAspect ||
        summaryMetadata?.focus_aspect ||
        null;
      const focusAspect = focusValue ? String(focusValue) : undefined;
      const summaryTypeValue =
        record.summary_type ||
        record.metadata?.summary_type ||
        record.metadata?.summaryType ||
        summaryMetadata?.summary_type ||
        'manual';
      const summaryType = summaryTypeValue ? String(summaryTypeValue) : 'manual';
      const fallbackFilename = buildFallbackFilename(
        sessionId || record.session_id || 'history',
        summaryType,
        focusAspect
      );

      if (record.pdf_url) {
        try {
          await downloadPdfFromUrl(record.pdf_url, fallbackFilename, authEmail);
          return;
        } catch (remoteErr) {
          console.warn('Falling back to client-side PDF generation for history item', remoteErr);
        }
      }

      try {
        const summaryText =
          (record.summary_text && record.summary_text.trim()) ||
          (summary && summary.trim()) ||
          'Summary is not available yet.';
        const blob = createFallbackPdfBlob({
          summaryText,
          citations: Array.isArray(record.citations) && record.citations.length ? record.citations : summaryCitations,
          focusAspect,
        });
        if (fallbackObjectUrlRef.current) {
          URL.revokeObjectURL(fallbackObjectUrlRef.current);
        }
        const objectUrl = URL.createObjectURL(blob);
        fallbackObjectUrlRef.current = objectUrl;
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = fallbackFilename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } catch (downloadErr) {
        console.error('Failed to download summary PDF fallback for history item', downloadErr);
      }
    },
    [authEmail, sessionId, summaryMetadata, summary, summaryCitations]
  );

  useEffect(
    () => () => {
      if (fallbackObjectUrlRef.current) {
        URL.revokeObjectURL(fallbackObjectUrlRef.current);
        fallbackObjectUrlRef.current = null;
      }
    },
    []
  );

  useEffect(() => {
    const selectedIds = Array.isArray(state?.selectedIds) ? state.selectedIds : state?.selectedIds ?? null;
    const snapshot = {
      summary,
      historyId,
      sessionId,
      initialPlan,
      summaryPdfUrl,
      summaryId,
      summaryHistory,
      activeSummaryId,
      summaryMetadata,
      summaryCitations,
      messages: messages.map((msg) => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
        metadata: msg.metadata,
      })),
      selectedIds,
      updatedAt: Date.now(),
    };
    writeSummaryReviewSnapshot(snapshot);
  }, [
    summary,
    historyId,
    sessionId,
    initialPlan,
    summaryPdfUrl,
    summaryId,
    summaryHistory,
    activeSummaryId,
    summaryMetadata,
    summaryCitations,
    messages,
    state,
  ]);

  const disableChat = !authEmail || initializing;

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', px: 2, py: 4 }}>
      <Button variant="text" onClick={() => navigate(-1)} sx={{ mb: 2 }}>
        ← Back
      </Button>

      <Typography variant="h4" fontWeight={600} gutterBottom>
        Summary Review
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Review the generated summary and let the AI know how you want to refine it.
      </Typography>

      {summaryHistory.length ? (
        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Summary History
            </Typography>
            <List dense disablePadding>
              {summaryHistory.map((record) => {
                const rawLabel =
                  record.summary_type ??
                  record.metadata?.summary_type ??
                  record.metadata?.summaryType ??
                  'Summary';
                const label = typeof rawLabel === 'string' ? rawLabel.replace(/_/g, ' ') : String(rawLabel);
                const timestamp = formatTimestamp(record.updated_at || record.created_at);
                const focusValue =
                  record.focus_aspect ||
                  record.metadata?.focus_aspect ||
                  record.metadata?.focusAspect ||
                  null;
                const focus = focusValue ? String(focusValue) : null;
                return (
                  <ListItem
                    key={record.id || `${label}-${timestamp}`}
                    disablePadding
                    secondaryAction={
                      record.pdf_url || record.summary_text ? (
                        <IconButton
                          edge="end"
                          aria-label="Download summary PDF"
                          size="small"
                          onClick={() => handleHistoryDownload(record)}
                        >
                          <PictureAsPdfIcon fontSize="small" />
                        </IconButton>
                      ) : null
                    }
                  >
                    <ListItemButton
                      selected={record.id === activeSummaryId}
                      onClick={() => handleHistorySelect(record)}
                    >
                      <ListItemText
                        primary={label}
                        secondary={[timestamp, focus ? `Focus: ${focus}` : null].filter(Boolean).join(' | ') || undefined}
                      />
                    </ListItemButton>
                  </ListItem>
                );
              })}
            </List>
          </CardContent>
        </Card>
      ) : null}

      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Generated Summary
          </Typography>
          {summary ? (
            <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
              {summary}
            </Typography>
          ) : initializing ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={20} />
              <Typography variant="body2">Loading summary…</Typography>
            </Stack>
          ) : initialPlan ? (
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                No AI-generated summary yet. Showing the latest research plan instead:
              </Typography>
              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                {initialPlan}
              </Typography>
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No summary yet. Generate a plan first, or wait for the assistant to respond.
            </Typography>
          )}
          {(summaryMetadata?.summary_type || summaryMetadata?.focus_aspect) && (
            <Stack spacing={0.25} sx={{ mt: 2 }}>
              {summaryMetadata?.summary_type ? (
                <Typography variant="body2" color="text.secondary">
                  Summary Type: {summaryMetadata.summary_type}
                </Typography>
              ) : null}
              {summaryMetadata?.focus_aspect ? (
                <Typography variant="body2" color="text.secondary">
                  Focus: {summaryMetadata.focus_aspect}
                </Typography>
              ) : null}
            </Stack>
          )}
          <Box sx={{ mt: 2 }}>
            <Button variant="outlined" onClick={handleDownloadClick}>
              Download Summary PDF
            </Button>
            {!summaryPdfUrl && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                A temporary PDF will download using the latest on-screen summary.
              </Typography>
            )}
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6">Refinement Chat</Typography>
            {sending && <CircularProgress size={18} />}
          </Stack>

          <Box
            sx={{
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 1,
              p: 2,
              maxHeight: 320,
              overflowY: 'auto',
              bgcolor: '#fafafa',
            }}
          >
            {messages.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {disableChat
                  ? 'Sign in to collaborate with the AI on adjustments.'
                  : 'Tell the AI what to refine—for example, “Highlight more recent studies” or “Expand on limitations.”'}
              </Typography>
            ) : (
              <Stack spacing={2}>
                {messages.map((msg, index) => (
                  <Box key={msg.id || `${msg.role}-${index}`}>
                    <Typography variant="overline" color="text.secondary">
                      {roleLabel[msg.role] || msg.role}
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {msg.content || (msg.pending ? 'Thinking…' : '')}
                    </Typography>
                    {msg.metadata?.citations?.length ? (
                      <Typography variant="caption" color="text.secondary">
                        Citations: {msg.metadata.citations.join(', ')}
                      </Typography>
                    ) : null}
                    {msg.pending ? (
                      <CircularProgress size={16} sx={{ mt: 0.5 }} />
                    ) : null}
                    {index < messages.length - 1 && <Divider sx={{ mt: 1 }} />}
                  </Box>
                ))}
              </Stack>
            )}
          </Box>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
            <TextField
              fullWidth
              multiline
              minRows={2}
              placeholder={
                disableChat
                  ? 'Sign in to chat with the AI.'
                  : 'Describe what to adjust—for example, “Focus on the methodology section.”'
              }
              value={input}
              onChange={(event) => setInput(event.target.value)}
              disabled={disableChat}
            />
            <Button
              variant="contained"
              color="primary"
              onClick={handleSend}
              disabled={disableChat || sending}
              sx={{ minWidth: 140 }}
            >
              Send
            </Button>
          </Stack>

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};

export default SummaryReviewPage;
