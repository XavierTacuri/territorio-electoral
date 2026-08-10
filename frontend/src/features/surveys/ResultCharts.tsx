import { Box, Typography } from '@mui/material';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { QuestionResult } from './types';
export default function ResultCharts({ questions }: { questions: QuestionResult[] }) {
  const chart = questions.find((x) => x.options.length > 0);
  if (!chart) return <Typography>No existen distribuciones categóricas para graficar.</Typography>;
  return (
    <Box role="img" aria-label={'Distribución de ' + chart.question_text} sx={{ height: 320 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chart.options}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Legend />
          <Bar dataKey="count" name="Respuestas" fill="#356a7c" />
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}
