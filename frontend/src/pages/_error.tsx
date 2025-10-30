function CustomError({
  statusCode,
}: {
  statusCode?: number;
}) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1rem",
        fontFamily: "system-ui, sans-serif",
        background: "#0b1520",
        color: "#f1f5f9",
      }}
    >
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>
        Something went wrong
      </h1>
      <p style={{ fontSize: "0.95rem", maxWidth: "32rem", textAlign: "center" }}>
        {statusCode
          ? `The server responded with status code ${statusCode}.`
          : "An unexpected client-side error occurred."}
      </p>
      <a
        href="/tender"
        style={{
          padding: "0.5rem 1.25rem",
          borderRadius: "0.5rem",
          border: "1px solid rgba(148, 163, 184, 0.4)",
          color: "#f1f5f9",
          textDecoration: "none",
        }}
      >
        Return to intake
      </a>
    </div>
  );
}

CustomError.getInitialProps = ({
  res,
  err,
}: {
  res?: { statusCode?: number };
  err?: { statusCode?: number };
}) => {
  const statusCode = res?.statusCode ?? err?.statusCode ?? 404;
  return { statusCode };
};

export default CustomError;
