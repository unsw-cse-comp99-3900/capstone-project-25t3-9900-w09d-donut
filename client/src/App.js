import React, { useState, useEffect } from 'react';
import {
  Box,
  Tabs,
  Tab,
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
  Chip,
  Stack,
  Alert,
} from '@mui/material';

function App() {
  const [tabIndex, setTabIndex] = useState(0);
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

  useEffect(() => {
    const savedHistory = JSON.parse(localStorage.getItem('searchHistory')) || [];
    setHistory(savedHistory);
  }, []);

  const handleTabChange = (event, newValue) => {
    setTabIndex(newValue);
  };

  const handleGeneratePlan = () => {
    setLoading(true);
    setResult(null);
    setTimeout(() => {
      const topic = researchTopic.trim() !== '' ? researchTopic : 'N/A';
      const goal = researchGoal || 'N/A';
      const time = timeWindow || 'N/A';
      const focus = focusType || 'N/A';
      const notes = text.trim() !== '' ? `\nNotes: ${text}` : '';

      setResult({
        plan: `Research Topic: ${topic}\nGoal: ${goal}\nTime Limit: ${time}\nFocus: ${focus}${notes}\n\nThis is a simulated research plan based on your inputs.`,
      });

      const newResult = {
        topic,
        goal,
        time,
        focus,
        notes,
        timestamp: new Date().toISOString(),
      };
      const existingHistory = JSON.parse(localStorage.getItem('searchHistory')) || [];
      const updatedHistory = [newResult, ...existingHistory].slice(0, 20);
      localStorage.setItem('searchHistory', JSON.stringify(updatedHistory));
      setHistory(updatedHistory);

      setLoading(false);
    }, 500);
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
      const response = await fetch('http://127.0.0.1:5000/upload_pdf', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      setUploadStatus('Uploaded successfully.');
      if (data.keywords && data.keywords.length > 0) {
        setKeywords(data.keywords);
      }
    } catch (error) {
      console.error(error);
      setUploadStatus('Upload failed.');
    }
  };

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto', mt: 4, px: 2 }}>
      <Card elevation={3}>
        <CardContent>
          <Typography variant="h5" gutterBottom fontWeight={600}>
            Research Plan Generator
          </Typography>
          <Tabs value={tabIndex} onChange={handleTabChange} textColor="primary" indicatorColor="primary" sx={{ mb: 3 }}>
            <Tab label="Topic / Question" />
            <Tab label="Keywords" />
            <Tab label="Upload PDFs" />
          </Tabs>

          {tabIndex === 0 && (
            <Box>
              <TextField
                label="Enter your research topic or question"
                variant="outlined"
                fullWidth
                multiline
                minRows={3}
                value={researchTopic}
                onChange={(e) => setResearchTopic(e.target.value)}
                sx={{ mb: 3 }}
                placeholder="Type your topic or question here..."
              />
              <TextField
                label="Additional Notes"
                variant="outlined"
                fullWidth
                multiline
                minRows={3}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Enter additional notes here..."
              />
            </Box>
          )}

          {tabIndex === 1 && (
            <Box>
              {keywords.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No keywords extracted yet. Please upload PDFs to extract keywords.
                </Typography>
              ) : (
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  {keywords.map((kw, idx) => (
                    <Chip key={idx} label={kw} color="primary" sx={{ mb: 1 }} />
                  ))}
                </Stack>
              )}
            </Box>
          )}

          {tabIndex === 2 && (
            <Box>
              <Button variant="contained" component="label" sx={{ mb: 2 }}>
                Select PDF Files
                <input type="file" hidden accept="application/pdf" multiple onChange={handleFileChange} />
              </Button>
              {pdfFiles.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="text.secondary">
                    Selected files:
                  </Typography>
                  <Stack direction="column" spacing={0.5} mt={0.5}>
                    {Array.from(pdfFiles).map((file, idx) => (
                      <Typography key={idx} variant="body2" noWrap>
                        {file.name}
                      </Typography>
                    ))}
                  </Stack>
                </Box>
              )}
              <Button
                variant="outlined"
                onClick={handleUpload}
                disabled={loading || pdfFiles.length === 0}
                sx={{ mb: 1 }}
              >
                Upload PDFs
              </Button>
              {uploadStatus && (
                <Alert severity={uploadStatus.includes('failed') ? 'error' : 'success'} sx={{ mt: 1 }}>
                  {uploadStatus}
                </Alert>
              )}
            </Box>
          )}

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
                <FormControl fullWidth>
                  <InputLabel id="time-window-label">Time Window</InputLabel>
                  <Select
                    labelId="time-window-label"
                    value={timeWindow}
                    label="Time Window"
                    onChange={(e) => setTimeWindow(e.target.value)}
                  >
                    <MenuItem value="Last 5 years">Last 5 years</MenuItem>
                    <MenuItem value="Last 3 years">Last 3 years</MenuItem>
                    <MenuItem value="Last 1 year">Last 1 year</MenuItem>
                  </Select>
                </FormControl>
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
                              setTabIndex(0);
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

          {result && (
            <Card variant="outlined" sx={{ mt: 4, bgcolor: '#f9f9f9' }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Generated Plan:
                </Typography>
                <Typography
                  variant="body1"
                  sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 14 }}
                >
                  {result.plan}
                </Typography>
              </CardContent>
            </Card>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}

export default App;