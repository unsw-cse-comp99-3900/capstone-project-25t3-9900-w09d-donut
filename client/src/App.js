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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Link as MuiLink,
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

  const handleLogout = () => {
    logoutAuth();
    setAuthUser(null);
    setHistory(readHistoryForUser(null));
    setResults([]);
    setResult(null);
    setError('');
    setShowHistory(false);
    window.dispatchEvent(new Event('auth:changed'));
  };

  const handleGeneratePlan = async () => {
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
      };

      const response = await axios.post(`${API_BASE_URL}/api/normal_search`, body);
      setResults(response.data.results || []);

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
      const response = await fetch(`${API_BASE_URL}/upload_pdf`, {
        method: 'POST',
        body: formData,
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
            <Button variant="contained" component="label" sx={{ mt: 1 }}>
              Upload PDFs
              <input type="file" hidden accept="application/pdf" multiple onChange={handleFileChange} />
            </Button>
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
                  <Typography variant="h6" gutterBottom>
                    💬 High-level Discussion
                  </Typography>

                  <Box
                    sx={{
                      height: 250,
                      overflowY: 'auto',
                      border: '1px solid #ccc',
                      borderRadius: 1,
                      p: 1,
                      mb: 2,
                      bgcolor: '#fafafa',
                    }}
                  >
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      <strong>AI:</strong> Hi! I&apos;m here for high-level discussion. Ask me anything about your research plan!
                    </Typography>
                  </Box>

                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <TextField
                      fullWidth
                      placeholder="Type your message here..."
                      variant="outlined"
                      size="small"
                    />
                    <Button variant="contained" color="primary">
                      Send
                    </Button>
                  </Box>
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
                    <TableCell><strong>Authors</strong></TableCell>
                    <TableCell><strong>Year</strong></TableCell>
                    <TableCell><strong>Title</strong></TableCell>
                    <TableCell><strong>Source</strong></TableCell>
                    <TableCell><strong>Cited</strong></TableCell>
                    <TableCell><strong>PDF</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {results.map((row, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{row.authors?.join(', ') || '-'}</TableCell>
                      <TableCell>{row.publication_date || '-'}</TableCell>
                      <TableCell>
                        <MuiLink href={row.link} target="_blank" rel="noopener">
                          {row.title}
                        </MuiLink>
                      </TableCell>
                      <TableCell>{row.source || '-'}</TableCell>
                      <TableCell>{row.cited_by_count || 0}</TableCell>
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
                  ))}
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
