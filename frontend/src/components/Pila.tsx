import { Stack as MuiStack, type StackProps } from "@mui/material";
import type { ResponsiveStyleValue } from "@mui/system";

type Alineacion = ResponsiveStyleValue<string>;

/** Stack que acepta alignItems/justifyContent como props (MUI 9 los quitó del componente). */
export function Stack({ alignItems, justifyContent, sx, ...r }: StackProps & { alignItems?: Alineacion; justifyContent?: Alineacion }) {
  return <MuiStack {...r} sx={{ alignItems, justifyContent, ...(sx as object) }} />;
}
