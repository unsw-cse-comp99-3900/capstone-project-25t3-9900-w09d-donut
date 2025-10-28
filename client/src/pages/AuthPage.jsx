import { useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

const AuthPage = () => {
  const [mode, setMode] = useState('login');

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', display: 'flex', alignItems: 'center', justifyContent: 'center', px: 2 }}>
      <Card sx={{ maxWidth: 420, width: '100%' }}>
        <CardContent>
          <Stack spacing={3}>
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
              onChange={(_, value) => setMode(value)}
              aria-label="auth mode"
              variant="fullWidth"
            >
              <Tab label="Sign In" value="login" />
              <Tab label="Sign Up" value="register" />
            </Tabs>

            <Stack spacing={2}>
              <TextField label="Email" type="email" fullWidth required />
              <TextField label="Password" type="password" fullWidth required />
              {mode === 'register' && <TextField label="Confirm Password" type="password" fullWidth required />}
            </Stack>

            <Button variant="contained" size="large">
              {mode === 'login' ? 'Sign In' : 'Sign Up'}
            </Button>

            <Typography variant="body2" color="text.secondary" textAlign="center">
              This screen is not wired to the backend yet. Connect your auth API when ready.
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};

export default AuthPage;
