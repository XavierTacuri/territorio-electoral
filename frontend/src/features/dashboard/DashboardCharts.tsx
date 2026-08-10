import { Grid, Paper, Typography } from '@mui/material';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
type Trend = { period_start: string; completed: number; planned: number; cancelled: number };
type Category = { name: string; mentions: number };
type Quality = { description: string; count: number };
function ChartBox({
  title,
  children,
  label,
}: {
  title: string;
  children: React.ReactNode;
  label: string;
}) {
  return (
    <Grid size={{ xs: 12, lg: 6 }}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h2">{title}</Typography>
        <div role="img" aria-label={label} style={{ height: 280 }}>
          {children}
        </div>
      </Paper>
    </Grid>
  );
}
export default function DashboardCharts({
  trends,
  needs,
  quality,
  alerts,
}: {
  trends: Trend[];
  needs: Category[];
  quality: Quality[];
  alerts: { name: string; count: number }[];
}) {
  return (
    <Grid container spacing={2}>
      <ChartBox title="Tendencia de actividades" label="Gráfica de líneas de actividades por fecha">
        <ResponsiveContainer>
          <LineChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period_start" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="completed" name="Completadas" stroke="#356a7c" />
            <Line type="monotone" dataKey="planned" name="Planificadas" stroke="#8a6f43" />
            <Line type="monotone" dataKey="cancelled" name="Canceladas" stroke="#6f6575" />
          </LineChart>
        </ResponsiveContainer>
      </ChartBox>
      <ChartBox title="Principales necesidades" label="Gráfica de menciones por necesidad">
        <ResponsiveContainer>
          <BarChart data={needs}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Bar dataKey="mentions" name="Menciones" fill="#557f65" />
          </BarChart>
        </ResponsiveContainer>
      </ChartBox>
      <ChartBox title="Calidad de datos" label="Gráfica de incidencias de calidad">
        <ResponsiveContainer>
          <BarChart data={quality}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="description" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Bar dataKey="count" name="Incidencias" fill="#7a6b88" />
          </BarChart>
        </ResponsiveContainer>
      </ChartBox>
      <ChartBox title="Alertas por severidad" label="Gráfica de alertas por severidad">
        <ResponsiveContainer>
          <BarChart data={alerts}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Bar dataKey="count" name="Alertas" fill="#9b633f" />
          </BarChart>
        </ResponsiveContainer>
      </ChartBox>
    </Grid>
  );
}
