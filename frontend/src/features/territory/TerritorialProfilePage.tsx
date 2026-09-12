import { useParams } from 'react-router-dom';
import { TerritorialProfileContent } from './TerritorialProfileContent';

export default function TerritorialProfilePage() {
  const { campaignId = '', parishId = '' } = useParams();
  return <TerritorialProfileContent campaignId={campaignId} parishId={parishId} />;
}
