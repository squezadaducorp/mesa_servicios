import { createTheme } from "@mui/material/styles";
import { esES } from "@mui/material/locale";

// Paleta tomada del logotipo de ADUCORP
export const marca = {
  navy: "#10203C",
  azulOscuro: "#0B255B",
  azul: "#1367AC",
  celeste: "#70A9CE",
  fondo: "#F4F6FA",
};

export const theme = createTheme(
  {
    palette: {
      primary: { main: marca.azul, dark: marca.azulOscuro, contrastText: "#fff" },
      secondary: { main: marca.celeste, contrastText: marca.navy },
      background: { default: marca.fondo, paper: "#fff" },
      text: { primary: "#1A2433", secondary: "#5A6577" },
      success: { main: "#2E7D32" },
      warning: { main: "#ED6C02" },
      error: { main: "#C62828" },
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: '"Inter", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      h4: { fontWeight: 700, color: marca.navy },
      h5: { fontWeight: 700, color: marca.navy },
      h6: { fontWeight: 600, color: marca.navy },
      button: { textTransform: "none", fontWeight: 600 },
    },
    components: {
      MuiPaper: { defaultProps: { elevation: 0 }, styleOverrides: { root: { border: "1px solid #E3E8F0" } } },
      MuiAppBar: { styleOverrides: { root: { border: "none" } } },
      MuiDrawer: { styleOverrides: { paper: { border: "none" } } },
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiTableCell: { styleOverrides: { head: { fontWeight: 600, color: marca.navy, backgroundColor: "#F8FAFD" } } },
      MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
      MuiTextField: { defaultProps: { size: "small" } },
      MuiSelect: { defaultProps: { size: "small" } },
    },
  },
  esES,
);
