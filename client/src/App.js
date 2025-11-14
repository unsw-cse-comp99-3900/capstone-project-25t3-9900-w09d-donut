import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box,
  TextField,
  Typography,
  Button,
  Card,
  CardContent,
  Grid,
  RadioGroup,
  FormControlLabel,
  Radio,
  Select,
  MenuItem,
  InputLabel,
  FormControl,
  Stack,
  Alert,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Link as MuiLink,
  Checkbox,
} from '@mui/material';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import { BrowserRouter as Router, Routes, Route, Link as RouterLink } from 'react-router-dom';
import AuthPage from './pages/AuthPage';
import { logout as logoutAuth } from './services/authApi';

const API_BASE_URL = (process.env.REACT_APP_API_BASE_URL || '').replace(/\/$/, '');
const HISTORY_STORAGE_KEY = 'searchHistoryByUser';

const readAuthSnapshot = () => {
  const email = localStorage.getItem('authEmail');
  if (!email) {
    return null;
  }
  const username = localStorage.getItem('authUsername') || email;
  return { email, username };
};

const resolveHistoryKey = (snapshot) => (snapshot?.email ? snapshot.email.toLowerCase() : 'guest');

const readHistoryMap = () => {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (err) {
    console.warn('Failed to parse stored history', err);
    return {};
  }
};

  const readLegacyHistory = () => {
  try {
    const raw = localStorage.getItem('searchHistory');
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    console.warn('Failed to parse legacy history', err);
    return [];
  }
};

const persistHistoryMap = (map) => {
  localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(map));
};

const readHistoryForUser = (snapshot) => {
  const key = resolveHistoryKey(snapshot);
  const map = readHistoryMap();
  if (map[key]) {
    return map[key];
  }

  const legacy = readLegacyHistory();
  if (legacy.length > 0) {
    map[key] = legacy;
    persistHistoryMap(map);
    localStorage.removeItem('searchHistory');
    return legacy;
  }

  return [];
};

const writeHistoryForUser = (snapshot, entries) => {
  const key = resolveHistoryKey(snapshot);
  const map = readHistoryMap();
  if (!entries.length) {
    delete map[key];
  } else {
    map[key] = entries;
  }
  persistHistoryMap(map);
};

const ResearchPlanner = () => {
  const [text, setText] = useState('');
  const [researchTopic, setResearchTopic] = useState('');
  const [researchGoal, setResearchGoal] = useState('Broad Survey');
  const [timeWindow, setTimeWindow] = useState('Last 5 years');
  const [focusType, setFocusType] = useState('Overview');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pdfFiles, setPdfFiles] = useState([]);
  const [uploadStatus, setUploadStatus] = useState('');
  const [keywords, setKeywords] = useState([]);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  const [results, setResults] = useState([]);
  const [error, setError] = useState('');
  const [resultLimit, setResultLimit] = useState(30);
  const [authUser, setAuthUser] = useState(() => readAuthSnapshot());
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const [chatSessionId, setChatSessionId] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatStatus, setChatStatus] = useState('');
  const [chatError, setChatError] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [selectedPaperIds, setSelectedPaperIds] = useState([]);
  const [refreshingStatus, setRefreshingStatus] = useState(false);
  const togglePaperSelection = (paperId) => {
    if (!paperId) {
      return;
    }
    setSelectedPaperIds((prev) =>
      prev.includes(paperId)
        ? prev.filter((id) => id !== paperId)
        : [...prev, paperId]
    );
  };

  const toggleSelectAll = (checked) => {
    if (!checked) {
      setSelectedPaperIds([]);
      return;
    }
    const ids = results.map((row) => row.paper_id).filter(Boolean);
    setSelectedPaperIds(ids);
  };
  const [deepResearchInstructions, setDeepResearchInstructions] = useState('');
  const [deepResearchResult, setDeepResearchResult] = useState(null);
  const [deepResearchError, setDeepResearchError] = useState('');
  const [deepResearchLoading, setDeepResearchLoading] = useState(false);

  useEffect(() => {
    const handleAuthChange = () => {
      setAuthUser(readAuthSnapshot());
    };

    const handleStorageChange = (event) => {
      if (event.key === 'authEmail' || event.key === 'authUsername') {
        handleAuthChange();
      }
      if (event.key === HISTORY_STORAGE_KEY) {
        setHistory(readHistoryForUser(readAuthSnapshot()));
      }
    };

    window.addEventListener('auth:changed', handleAuthChange);
    window.addEventListener('storage', handleStorageChange);

    return () => {
      window.removeEventListener('auth:changed', handleAuthChange);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  useEffect(() => {
    setHistory(readHistoryForUser(authUser));
  }, [authUser]);

  useEffect(() => {
    setDeepResearchResult(null);
    setDeepResearchError('');
    setSelectedPaperIds([]);
  }, [activeHistoryId]);

  const resolveAuthEmail = () => authUser?.email || localStorage.getItem('authEmail') || '';
  const canChat = Boolean(activeHistoryId && resolveAuthEmail());

  const buildAuthHeaders = () => {
    const email = resolveAuthEmail();
    return email ? { 'X-User-Email': email } : {};
  };

  const normalizePapers = (items) =>
    (items || []).map((item, index) => {
      const rawAuthors = item.authors || item.author_names || [];
      let authors = [];
      if (Array.isArray(rawAuthors)) {
        authors = rawAuthors;
      } else if (typeof rawAuthors === 'string') {
        authors = rawAuthors.split(/[,;]+/).map((author) => author.trim()).filter(Boolean);
      }
      const paperId = item.paper_id || item.id || item.link || item.url || `paper-${index}`;
      return {
        paper_id: paperId,
        title: item.title || item.display_name || 'Untitled',
        authors,
        publication_date: item.publication_date || item.year || '',
        publication_year: item.publication_year || item.year,
        source: item.source || item.journal || '',
        cited_by_count: item.cited_by_count ?? item.citations ?? 0,
        link: item.link || item.url || paperId,
        pdf_url: item.pdf_url || item.pdf || '',
        selected: item.selected !== undefined ? Boolean(item.selected) : true,
        full_text: item.full_text || '',
        structured_sections: item.structured_sections || {},
        chunks: item.chunks || [],
      };
    });

  const refreshSelectionFromPapers = (papers) => {
    const selectedIds = papers.filter((paper) => paper.selected !== false && paper.paper_id).map((paper) => paper.paper_id);
    setSelectedPaperIds(selectedIds);
  };

  const fetchHistoryDetails = async (historyId) => {
    const email = resolveAuthEmail();
    if (!historyId || !email) {
      return null;
    }
    try {
      const response = await axios.get(`${API_BASE_URL}/api/search/history/${historyId}`, {
        headers: buildAuthHeaders(),
      });
      const historyRecord = response.data.history;
      if (!historyRecord) {
        return null;
      }
      const normalized = normalizePapers(historyRecord.papers || []);
      setResults(normalized);
      refreshSelectionFromPapers(normalized);
      return normalized;
    } catch (historyErr) {
      console.error(historyErr);
      setChatError(historyErr?.response?.data?.error || 'Unable to refresh paper selection.');
      return null;
    }
  };

  const handleRefreshStatuses = async () => {
    if (!activeHistoryId) {
      return;
    }
    setRefreshingStatus(true);
    try {
      await fetchHistoryDetails(activeHistoryId);
    } catch (err) {
      console.error(err);
    } finally {
      setRefreshingStatus(false);
    }
  };

  const resetChatState = () => {
    setActiveHistoryId(null);
    setChatSessionId(null);
    setChatMessages([]);
    setChatInput('');
    setChatStatus('');
    setChatError('');
    setSelectedPaperIds([]);
    setDeepResearchInstructions('');
    setDeepResearchResult(null);
    setDeepResearchError('');
  };

  const bootstrapChatSession = async (historyId) => {
    if (!historyId) {
      setChatError('Run a search with your account to start chatting.');
      return null;
    }
    const email = resolveAuthEmail();
    if (!email) {
      setChatError('Please sign in to use the AI assistant.');
      return null;
    }
    setChatStatus('Connecting to AI assistant...');
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/chat/sessions`,
        {
          history_id: historyId,
          user_email: email,
        },
        {
          headers: buildAuthHeaders(),
        }
      );
      setChatSessionId(response.data.session_id);
      setChatMessages(response.data.messages || []);
      setChatStatus('Ready to chat');
      setChatError('');
      return response.data.session_id;
    } catch (sessionErr) {
      console.error(sessionErr);
      setChatStatus('');
      setChatError(sessionErr?.response?.data?.error || 'Unable to start AI chat session.');
      return null;
    }
  };

  const handleLogout = () => {
    logoutAuth();
    setAuthUser(null);
    setHistory(readHistoryForUser(null));
    setResults([]);
    setResult(null);
    setError('');
    setShowHistory(false);
    resetChatState();
    window.dispatchEvent(new Event('auth:changed'));
  };

  const handleGeneratePlan = async () => {
    resetChatState();
    setLoading(true);
    setResult(null);
    setError('');
    setResults([]);

    try {
      const keywordsArray = researchTopic
        ? researchTopic.split(/[,，\s]+/).filter(Boolean)
        : [];

      const similarHistory = history.filter((item) =>
        researchTopic.toLowerCase().includes(item.topic.toLowerCase())
      );
      if (similarHistory.length > 0) {
        console.log('⚡ Found similar past searches:', similarHistory);
      }

      const body = {
        keywords: keywordsArray,
        date_range: ['2020-01-01', '2025-01-01'],
        concepts: null,
        limit: resultLimit,
        ...(resolveAuthEmail() ? { user_email: resolveAuthEmail() } : {}),
      };

      const response = await axios.post(`${API_BASE_URL}/api/normal_search`, body, {
        headers: buildAuthHeaders(),
      });
      const normalizedResults = normalizePapers(response.data.results || []);
      setResults(normalizedResults);
      refreshSelectionFromPapers(normalizedResults);

      const historyId = response.data.history_id || null;
      setActiveHistoryId(historyId);
      if (historyId && resolveAuthEmail()) {
        await fetchHistoryDetails(historyId);
        await bootstrapChatSession(historyId);
      }

      const topic = researchTopic.trim() || 'N/A';
      const goal = researchGoal || 'N/A';
      const time = timeWindow || 'N/A';
      const focus = focusType || 'N/A';
      const notes = text.trim() ? `\nNotes: ${text}` : '';

      setResult({
        plan: `Research Topic: ${topic}\nGoal: ${goal}\nTime Limit: ${time}\nFocus: ${focus}${notes}\n\nSearch completed successfully.`,
      });

  const newResult = { topic, goal, time, focus, notes, timestamp: new Date().toISOString() };
  const snapshot = readAuthSnapshot() || authUser;
  const existingHistory = readHistoryForUser(snapshot);
      const updatedHistory = [newResult, ...existingHistory].slice(0, 20);
      writeHistoryForUser(snapshot, updatedHistory);
      setHistory(updatedHistory);
    } catch (err) {
      console.error(err);
      setError('Failed to fetch search results. Please check backend connection.');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setText('');
    setResearchTopic('');
    setResearchGoal('Broad Survey');
    setTimeWindow('Last 5 years');
    setFocusType('Overview');
    setResult(null);
    setLoading(false);
    setPdfFiles([]);
    setUploadStatus('');
    setKeywords([]);
    setResults([]);
    setError('');
    setShowHistory(false);
    resetChatState();
  };

  const handleFileChange = (e) => {
    setPdfFiles(e.target.files);
  };

  const handleUpload = async () => {
    if (pdfFiles.length === 0) {
      setUploadStatus('Please select at least one PDF file.');
      return;
    }

    const formData = new FormData();
    for (let i = 0; i < pdfFiles.length; i++) {
      formData.append('files', pdfFiles[i]);
    }

    setUploadStatus('Uploading...');
    try {
      const uploadHeaders = buildAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/upload_pdf`, {
        method: 'POST',
        body: formData,
        headers: Object.keys(uploadHeaders).length ? uploadHeaders : undefined,
      });
      const data = await response.json();
      setUploadStatus('Uploaded successfully.');
      if (data.keywords && data.keywords.length > 0) {
        setKeywords(data.keywords);
      }
    } catch (uploadError) {
      console.error(uploadError);
      setUploadStatus('Upload failed.');
    }
  };

  const sendChatMessage = async (rawMessage, options = {}) => {
    const trimmed = (rawMessage || '').trim();
    if (!trimmed) {
      return;
    }
    if (!activeHistoryId) {
      setChatError('Please run a logged-in search before chatting.');
      return;
    }
    const email = resolveAuthEmail();
    if (!email) {
      setChatError('Please sign in to chat with the AI assistant.');
      return;
    }
    setChatLoading(true);
    setChatError('');
    let sessionId = chatSessionId;
    if (!sessionId) {
      sessionId = await bootstrapChatSession(activeHistoryId);
      if (!sessionId) {
        setChatLoading(false);
        return;
      }
    }
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/chat/sessions/${sessionId}/messages`,
        {
          message: trimmed,
          user_email: email,
        },
        {
          headers: buildAuthHeaders(),
        }
      );
      setChatMessages(response.data.messages || []);
      if (options.clearInput) {
        setChatInput('');
      }
      if (Array.isArray(response.data.selected_ids)) {
        setSelectedPaperIds(response.data.selected_ids);
      }
      if (activeHistoryId) {
        await fetchHistoryDetails(activeHistoryId);
      }
    } catch (chatErr) {
      console.error(chatErr);
      setChatError(chatErr?.response?.data?.error || 'Assistant failed to respond. Please try again.');
    } finally {
      setChatLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim()) {
      return;
    }
    await sendChatMessage(chatInput, { clearInput: true });
  };

  const handleDeepResearch = async () => {
    if (!activeHistoryId) {
      setDeepResearchError('Please select a search history item before running deep research.');
      return;
    }
    if (selectedPaperIds.length === 0) {
      setDeepResearchError('Select at least one paper to analyse.');
      return;
    }
    setDeepResearchLoading(true);
    setDeepResearchError('');
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/deep_research`,
        {
          history_id: activeHistoryId,
          paper_ids: selectedPaperIds,
          instructions: deepResearchInstructions || undefined,
        },
        { headers: buildAuthHeaders() }
      );
      setDeepResearchResult(response.data);
    } catch (err) {
      console.error(err);
      setDeepResearchResult(null);
      setDeepResearchError(err?.response?.data?.error || 'Deep research failed. Please try again.');
    } finally {
      setDeepResearchLoading(false);
    }
  };

  const handleSummaryCandidateClick = async (candidate, index) => {
    if (chatLoading || !candidate) {
      return;
    }
    const identifier = candidate.paper_id || candidate.short_id || `paper ${index + 1}`;
    const prompt = `Summarize ${identifier}`;
    await sendChatMessage(prompt);
  };

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto', mt: 4, px: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
        {authUser ? (
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body1" fontWeight={500}>
              {authUser.username}
            </Typography>
            <Button variant="text" onClick={handleLogout}>
              Log Out
            </Button>
          </Stack>
        ) : (
          <Button component={RouterLink} to="/auth" variant="outlined">
            Sign In / Sign Up
          </Button>
        )}
      </Box>
      <Card elevation={3}>
        <CardContent>
          <Typography variant="h5" gutterBottom fontWeight={600}>
            Research Plan Generator
          </Typography>
          <Box sx={{ mb: 3 }}>
            <TextField
              label="Enter your research topic, keywords, or question"
              variant="outlined"
              fullWidth
              multiline
              minRows={3}
              value={researchTopic}
              onChange={(e) => setResearchTopic(e.target.value)}
              placeholder="Type your research topic, keywords, or upload related files..."
              sx={{ mb: 2 }}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }}>
              <Button variant="contained" component="label">
                Upload PDFs
                <input type="file" hidden accept="application/pdf" multiple onChange={handleFileChange} />
              </Button>
              <Button variant="outlined" onClick={handleUpload} disabled={pdfFiles.length === 0}>
                Process Upload
              </Button>
            </Stack>
            {pdfFiles.length > 0 && (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" color="text.secondary">Selected files:</Typography>
                {Array.from(pdfFiles).map((file, idx) => (
                  <Box
                    key={idx}
                    sx={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      borderBottom: '1px solid #eee',
                      py: 0.5,
                    }}
                  >
                    <Typography variant="body2">{file.name}</Typography>
                    <Button
                      size="small"
                      color="error"
                      onClick={() => {
                        const newFiles = Array.from(pdfFiles).filter((_, i) => i !== idx);
                        setPdfFiles(newFiles);
                      }}
                    >
                      Remove
                    </Button>
                  </Box>
                ))}
              </Box>
            )}
            {uploadStatus && (
              <Alert severity={uploadStatus.includes('failed') ? 'error' : 'success'} sx={{ mt: 1 }}>
                {uploadStatus}
              </Alert>
            )}
            {keywords.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Suggested keywords from PDF upload (click to add):
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {keywords.map((word) => (
                    <Chip
                      key={word}
                      label={word}
                      size="small"
                      onClick={() =>
                        setResearchTopic((prev) =>
                          prev.includes(word) ? prev : `${prev ? `${prev}, ` : ''}${word}`
                        )
                      }
                      sx={{ mb: 1 }}
                    />
                  ))}
                </Stack>
              </Box>
            )}
          </Box>

          <Card variant="outlined" sx={{ mt: 4, p: 2, bgcolor: 'background.paper' }}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={4}>
                <FormControl fullWidth>
                  <InputLabel id="research-goal-label">Research Goal</InputLabel>
                  <Select
                    labelId="research-goal-label"
                    value={researchGoal}
                    label="Research Goal"
                    onChange={(e) => setResearchGoal(e.target.value)}
                  >
                    <MenuItem value="Broad Survey">Broad Survey</MenuItem>
                    <MenuItem value="Deep Dive">Deep Dive</MenuItem>
                    <MenuItem value="Novelty / Innovation Scan">Novelty / Innovation Scan</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid item xs={12} md={4}>
                <TextField
                  label="Time Window (years)"
                  type="number"
                  value={timeWindow}
                  onChange={(e) => setTimeWindow(e.target.value)}
                  InputProps={{ inputProps: { min: 1, max: 10 } }}
                  InputLabelProps={{ shrink: true }}
                  fullWidth
                  sx={{ minWidth: 180 }}
                />
              </Grid>

              <Grid item xs={12} md={4}>
                <TextField
                  label="Most Compatible (number of papers)"
                  type="number"
                  value={resultLimit}
                  onChange={(e) => setResultLimit(Number(e.target.value))}
                  InputProps={{ inputProps: { min: 5, max: 200 } }}
                  InputLabelProps={{ shrink: true }}
                  fullWidth
                  sx={{ minWidth: 250 }}
                />
              </Grid>

              <Grid item xs={12} md={4}>
                <Typography variant="subtitle1" gutterBottom>
                  Focus Type
                </Typography>
                <RadioGroup
                  row
                  value={focusType}
                  onChange={(e) => setFocusType(e.target.value)}
                  aria-label="focus-type"
                  name="focus-type"
                >
                  <FormControlLabel value="Overview" control={<Radio />} label="Overview" />
                  <FormControlLabel value="Detail" control={<Radio />} label="Detail" />
                  <FormControlLabel value="Summary" control={<Radio />} label="Summary" />
                </RadioGroup>
              </Grid>
            </Grid>
          </Card>

          <Box sx={{ mt: 4, textAlign: 'center' }}>
            <Button
              variant="contained"
              color="primary"
              size="large"
              onClick={handleGeneratePlan}
              disabled={loading}
              sx={{ minWidth: 180, fontWeight: 600 }}
            >
              {loading ? 'Loading...' : 'Generate Plan'}
            </Button>
            <Button
              variant="text"
              color="secondary"
              onClick={handleClear}
              disabled={loading}
              sx={{ ml: 2 }}
            >
              Clear
            </Button>
          </Box>

          <Box sx={{ mt: 4 }}>
            <Button
              variant="outlined"
              onClick={() => setShowHistory(!showHistory)}
              size="small"
            >
              {showHistory ? 'Hide History' : 'Show History'}
            </Button>
            <Button
              variant="text"
              size="small"
              sx={{ ml: 1 }}
              disabled={!activeHistoryId || refreshingStatus}
              onClick={handleRefreshStatuses}
            >
              {refreshingStatus ? 'Refreshing…' : 'Refresh Parsed Status'}
            </Button>
            {showHistory && (
              <Card variant="outlined" sx={{ mt: 2, p: 2, maxHeight: 300, overflowY: 'auto' }}>
                <Typography variant="h6" gutterBottom>
                  Search History (last 7 days)
                </Typography>
                {history.length === 0 ? (
                  <Typography>No history yet.</Typography>
                ) : (
                  <Box component="ul" sx={{ pl: 2, m: 0 }}>
                    {history
                      .filter((h) => new Date() - new Date(h.timestamp) < 7 * 24 * 60 * 60 * 1000)
                      .map((item, index) => (
                        <Box
                          component="li"
                          key={index}
                          sx={{
                            mb: 1,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            flexWrap: 'wrap',
                          }}
                        >
                          <Typography variant="body2" sx={{ flexGrow: 1, minWidth: 0 }}>
                            <strong>{item.topic}</strong> — {item.goal}, {item.time}, {item.focus}
                          </Typography>
                          <Button
                            size="small"
                            onClick={() => {
                              setResearchTopic(item.topic);
                              setResearchGoal(item.goal);
                              setTimeWindow(item.time);
                              setFocusType(item.focus);
                              setText(item.notes);
                            }}
                            sx={{ ml: 1 }}
                            variant="outlined"
                          >
                            Load
                          </Button>
                        </Box>
                      ))}
                  </Box>
                )}
              </Card>
            )}
          </Box>

          {results.length > 0 && (
            <Typography variant="subtitle1" sx={{ mt: 2, fontWeight: 500 }}>
              Showing top {results.length} results
            </Typography>
          )}

          {result && (
            <>
              <Card variant="outlined" sx={{ mt: 4, bgcolor: '#f9f9f9' }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Generated Plan:
                  </Typography>
                  <TextField
                    label="Generated Research Plan"
                    multiline
                    fullWidth
                    minRows={6}
                    value={result.plan}
                    onChange={(e) => setResult({ ...result, plan: e.target.value })}
                    sx={{ fontFamily: 'monospace', fontSize: 14 }}
                  />
                </CardContent>
              </Card>

              <Box sx={{ mt: 5 }}>
                <Card variant="outlined" sx={{ p: 2 }}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} spacing={1}>
                    <Typography variant="h6">
                      💬 AI Conversation
                    </Typography>
                    {chatStatus && (
                      <Typography variant="body2" color="text.secondary">
                        {chatStatus}
                      </Typography>
                    )}
                  </Stack>

                  {chatError && (
                    <Alert severity="error" sx={{ mt: 2 }}>
                      {chatError}
                    </Alert>
                  )}

                  <Box
                    sx={{
                      height: 260,
                      overflowY: 'auto',
                      border: '1px solid #ccc',
                      borderRadius: 1,
                      p: 1.5,
                      my: 2,
                      bgcolor: '#fafafa',
                    }}
                  >
                    {chatMessages.length === 0 ? (
                      <Typography variant="body2" color="text.secondary">
                        {canChat
                          ? 'Start the conversation to discuss these results with the AI assistant.'
                          : 'Sign in and run a search to enable the AI conversation experience.'}
                      </Typography>
                    ) : (
                      chatMessages.map((msg, index) => {
                        const isUser = msg.role === 'user';
                        const rawMetadata = msg.metadata?.metadata || msg.metadata || {};
                        const summaryCandidates = !isUser && Array.isArray(rawMetadata.summary_candidates) ? rawMetadata.summary_candidates : [];
                        const summaryPending = !isUser && (rawMetadata.summary_pending || summaryCandidates.length > 0);
                        return (
                          <Box
                            key={`${msg.role}-${index}-${msg.created_at || index}`}
                            sx={{
                              mb: 1.5,
                              textAlign: isUser ? 'right' : 'left',
                            }}
                          >
                            <Typography variant="caption" color="text.secondary">
                              {isUser ? 'You' : 'Assistant'}
                            </Typography>
                            <Typography
                              variant="body2"
                              sx={{
                                display: 'inline-block',
                                px: 1.5,
                                py: 1,
                                borderRadius: 2,
                                bgcolor: isUser ? 'primary.light' : 'grey.200',
                                color: 'text.primary',
                                whiteSpace: 'pre-line',
                                mt: 0.5,
                              }}
                            >
                              {msg.content}
                            </Typography>
                            {!isUser && summaryCandidates.length > 0 && (
                              <Box sx={{ mt: 1.5, textAlign: 'left' }}>
                                <Typography variant="caption" color="text.secondary">
                                  Choose a parsed paper to summarize:
                                </Typography>
                                <Stack spacing={1} sx={{ mt: 1 }}>
                                  {summaryCandidates.map((candidate, candidateIndex) => {
                                    const position = candidate.position || candidateIndex + 1;
                                    const source = candidate.source || 'Unknown venue';
                                    const year = candidate.year ? `${candidate.year}` : null;
                                    const descriptor = [year, source].filter(Boolean).join(' · ');
                                    return (
                                      <Card variant="outlined" key={`${candidate.paper_id || candidate.short_id || candidateIndex}`}>
                                        <CardContent sx={{ py: 1.5 }}>
                                          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                            {position}. {candidate.title || candidate.short_id || 'Untitled'}
                                          </Typography>
                                          {descriptor && (
                                            <Typography variant="body2" color="text.secondary">
                                              {descriptor}
                                            </Typography>
                                          )}
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                                            ID: {candidate.short_id || candidate.paper_id}
                                          </Typography>
                                          <Button
                                            size="small"
                                            sx={{ mt: 1 }}
                                            variant="contained"
                                            onClick={() => handleSummaryCandidateClick(candidate, candidateIndex)}
                                            disabled={!canChat || chatLoading}
                                          >
                                            Summarize this paper
                                          </Button>
                                        </CardContent>
                                      </Card>
                                    );
                                  })}
                                </Stack>
                              </Box>
                            )}
                            {!isUser && summaryPending && summaryCandidates.length === 0 && (
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                                Waiting for parsed papers. As soon as text is available, selectable options will appear here.
                              </Typography>
                            )}
                          </Box>
                        );
                      })
                    )}
                  </Box>

                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <TextField
                      fullWidth
                      placeholder={canChat ? 'Ask about the retrieved papers...' : 'Sign in and run a search to chat'}
                      variant="outlined"
                      size="small"
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      disabled={!canChat || chatLoading}
                    />
                    <Button
                      variant="contained"
                      color="primary"
                      onClick={handleSendMessage}
                      disabled={!canChat || chatLoading || !chatInput.trim()}
                    >
                      {chatLoading ? 'Sending...' : 'Send'}
                    </Button>
                  </Box>
              </Card>
            </Box>

            <Box sx={{ mt: 4 }}>
              <Card variant="outlined">
                <CardContent>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }}>
                    <Box>
                      <Typography variant="h6">Deep Research</Typography>
                      <Typography variant="body2" color="text.secondary">
                        Select papers from the table and provide optional focus instructions to generate a deeper synthesis.
                      </Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      Selected papers: {selectedPaperIds.length}
                    </Typography>
                  </Stack>

                  <TextField
                    label="Focus or instructions"
                    multiline
                    minRows={2}
                    fullWidth
                    sx={{ mt: 2 }}
                    value={deepResearchInstructions}
                    onChange={(e) => setDeepResearchInstructions(e.target.value)}
                    placeholder="e.g., Highlight emerging gaps and policy implications"
                  />

                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 2 }}>
                    <Button
                      variant="contained"
                      color="secondary"
                      onClick={handleDeepResearch}
                      disabled={deepResearchLoading || selectedPaperIds.length === 0 || !activeHistoryId}
                    >
                      {deepResearchLoading ? 'Running...' : 'Run Deep Research'}
                    </Button>
                    <Button
                      variant="text"
                      disabled={!deepResearchInstructions && !deepResearchResult}
                      onClick={() => {
                        setDeepResearchInstructions('');
                        setDeepResearchResult(null);
                        setDeepResearchError('');
                      }}
                    >
                      Clear
                    </Button>
                  </Stack>

                  {deepResearchError && (
                    <Alert severity="error" sx={{ mt: 2 }}>
                      {deepResearchError}
                    </Alert>
                  )}

                  {deepResearchResult && (
                    <Box sx={{ mt: 3 }}>
                      <Typography variant="subtitle1" gutterBottom>
                        Round Findings
                      </Typography>
                      {(deepResearchResult.round?.findings || []).length ? (
                        <Box component="ul" sx={{ pl: 3 }}>
                          {deepResearchResult.round.findings.map((finding, idx) => (
                            <li key={idx}>{finding}</li>
                          ))}
                        </Box>
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          No findings were generated.
                        </Typography>
                      )}

                      {(deepResearchResult.round?.missing || []).length > 0 && (
                        <>
                          <Typography variant="subtitle1" sx={{ mt: 2 }}>
                            Gaps to explore
                          </Typography>
                          <Box component="ul" sx={{ pl: 3 }}>
                            {deepResearchResult.round.missing.map((gap, idx) => (
                              <li key={idx}>{gap}</li>
                            ))}
                          </Box>
                        </>
                      )}

                      {(deepResearchResult.query_suggestions || []).length > 0 && (
                        <>
                          <Typography variant="subtitle1" sx={{ mt: 2 }}>
                            Suggested next queries
                          </Typography>
                          <Box component="ul" sx={{ pl: 3 }}>
                            {deepResearchResult.query_suggestions.map((item, idx) => (
                              <li key={idx}>{item.query}</li>
                            ))}
                          </Box>
                        </>
                      )}

                      {deepResearchResult.report && (
                        <Box sx={{ mt: 3 }}>
                          <Typography variant="subtitle1" gutterBottom>
                            Final memo
                          </Typography>
                          <Box
                            component="pre"
                            sx={{
                              whiteSpace: 'pre-wrap',
                              bgcolor: '#f5f5f5',
                              p: 2,
                              borderRadius: 1,
                              maxHeight: 320,
                              overflowY: 'auto',
                            }}
                          >
                            {deepResearchResult.report}
                          </Box>
                        </Box>
                      )}
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Box>
            </>
          )}
          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}

          {loading && (
            <Box sx={{ mt: 3, textAlign: 'center' }}>
              <CircularProgress />
              <Typography variant="body2" sx={{ mt: 1 }}>Searching...</Typography>
            </Box>
          )}

          {!loading && results.length > 0 && (
            <TableContainer component={Paper} sx={{ mt: 3 }}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox">
                      <Checkbox
                        indeterminate={selectedPaperIds.length > 0 && selectedPaperIds.length < results.length}
                        checked={results.length > 0 && selectedPaperIds.length === results.length}
                        onChange={(e) => toggleSelectAll(e.target.checked)}
                      />
                    </TableCell>
                    <TableCell><strong>Authors</strong></TableCell>
                    <TableCell><strong>Year</strong></TableCell>
                    <TableCell><strong>Title</strong></TableCell>
                    <TableCell><strong>Source</strong></TableCell>
                    <TableCell><strong>Cited</strong></TableCell>
                    <TableCell><strong>Status</strong></TableCell>
                    <TableCell><strong>PDF</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {results.map((row, idx) => {
                    const isSelected = selectedPaperIds.includes(row.paper_id);
                    return (
                      <TableRow
                        key={row.paper_id || idx}
                        selected={isSelected}
                        sx={{ bgcolor: isSelected ? 'rgba(25, 118, 210, 0.08)' : undefined }}
                      >
                        <TableCell padding="checkbox">
                          <Checkbox
                            checked={isSelected}
                            onChange={() => togglePaperSelection(row.paper_id)}
                            disabled={!row.paper_id}
                          />
                        </TableCell>
                        <TableCell>{Array.isArray(row.authors) && row.authors.length ? row.authors.join(', ') : '-'}</TableCell>
                        <TableCell>{row.publication_date || row.publication_year || '-'}</TableCell>
                        <TableCell>
                          <MuiLink href={row.link} target="_blank" rel="noopener">
                            {row.title}
                          </MuiLink>
                        </TableCell>
                        <TableCell>{row.source || '-'}</TableCell>
                        <TableCell>{row.cited_by_count || 0}</TableCell>
                        <TableCell>
                          {row.full_text ? (
                            <Chip label="Parsed" color="success" size="small" />
                          ) : (
                            <Chip label="Not Parsed" color="warning" size="small" />
                          )}
                        </TableCell>
                        <TableCell>
                          {row.pdf_url ? (
                            <MuiLink href={row.pdf_url} target="_blank" rel="noopener">
                              <PictureAsPdfIcon color="error" />
                            </MuiLink>
                          ) : (
                            '-'
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};

const App = () => (
  <Router>
    <Routes>
      <Route path="/" element={<ResearchPlanner />} />
      <Route path="/auth" element={<AuthPage />} />
    </Routes>
  </Router>
);

export default App;
