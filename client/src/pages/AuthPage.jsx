import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { loginApi, registerApi } from '../services/authApi';

const AuthPage = () => {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [username, setUsername] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const navigate = useNavigate();

  const resetFeedback = () => {
    setError('');
    setSuccess('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    resetFeedback();

    if (!email || !password || (mode === 'register' && !username)) {
      setError('Please fill in all required fields.');
      return;
    }

    if (mode === 'register' && password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);

    try {
      if (mode === 'register') {
        await registerApi({ username, email, password });
        localStorage.setItem('authUsername', username);
        setSuccess('Account created successfully. Please sign in.');
        setMode('login');
        setPassword('');
        setConfirmPassword('');
      } else {
        const response = await loginApi({ email, password });
        const displayName = response?.username || localStorage.getItem('authUsername') || email;
        localStorage.setItem('authUsername', displayName);
        window.dispatchEvent(new Event('auth:changed'));
        setSuccess('Signed in successfully. Redirecting...');
        navigate('/', { replace: true });
      }
    } catch (err) {
      setError(err.message || 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  const handleModeChange = (_, value) => {
    setMode(value);
    resetFeedback();
    setPassword('');
    setConfirmPassword('');
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex', alignItems: 'center', justifyContent: 'center', px: 2 }}>
      <Card sx={{ maxWidth: 420, width: '100%' }}>
        <CardContent>
          <Stack spacing={3} component="form" onSubmit={handleSubmit} noValidate>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="h5" fontWeight={600}>
                {mode === 'login' ? 'Sign In' : 'Sign Up'}
              </Typography>
              <Button component={RouterLink} to="/" variant="text">
                Back to Home
              </Button>
            </Box>

            <Tabs
              value={mode}
              onChange={handleModeChange}
              aria-label="auth mode"
              variant="fullWidth"
            >
              <Tab label="Sign In" value="login" />
              <Tab label="Sign Up" value="register" />
            </Tabs>

            <Stack spacing={2}>
              {mode === 'register' && (
                <TextField
                  label="Username"
                  fullWidth
                  required
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              )}
              <TextField
                label="Email"
                type="email"
                fullWidth
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <TextField
                label="Password"
                type="password"
                fullWidth
                required
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              {mode === 'register' && (
                <TextField
                  label="Confirm Password"
                  type="password"
                  fullWidth
                  required
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                />
              )}
            </Stack>

            <Button
              type="submit"
              variant="contained"
              size="large"
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : mode === 'login' ? 'Sign In' : 'Sign Up'}
            </Button>

            {error && (
              <Alert severity="error">{error}</Alert>
            )}

            {success && (
              <Alert severity="success">{success}</Alert>
            )}

            <Typography variant="body2" color="text.secondary" textAlign="center">
              Your credentials are sent securely to the backend authentication service.
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};

export default AuthPage;
