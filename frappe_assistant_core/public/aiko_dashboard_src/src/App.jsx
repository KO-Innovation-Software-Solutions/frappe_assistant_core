import { OpenUIDashboard } from "./components/OpenUIDashboard";
import { library } from "./library";
import { STARTERS } from "./starters";

export default function App() {
  return <OpenUIDashboard library={library} starters={STARTERS} />;
}
