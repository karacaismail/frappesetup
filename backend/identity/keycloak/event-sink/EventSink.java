// Development-only receiver for the event listener tests. It records every request and answers 202.
// It does not verify signatures: the tests verify them against the contract. Never deploy it.
import com.sun.net.httpserver.HttpServer;
import java.io.FileWriter;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class EventSink {
    private static final int MAX_BODY_BYTES = 1 << 20;

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", 8080), 0);
        server.createContext("/", exchange -> {
            byte[] body = exchange.getRequestBody().readNBytes(MAX_BODY_BYTES);
            String line = "{\"method\":" + quote(exchange.getRequestMethod())
                    + ",\"path\":" + quote(exchange.getRequestURI().toString())
                    + ",\"content_type\":" + quote(exchange.getRequestHeaders().getFirst("Content-Type"))
                    + ",\"timestamp\":" + quote(exchange.getRequestHeaders().getFirst("X-Identity-Sync-Timestamp"))
                    + ",\"signature\":" + quote(exchange.getRequestHeaders().getFirst("X-Identity-Sync-Signature"))
                    + ",\"body\":" + quote(Base64.getEncoder().encodeToString(body)) + "}\n";
            synchronized (EventSink.class) {
                try (FileWriter out = new FileWriter("/tmp/requests.jsonl", StandardCharsets.UTF_8, true)) {
                    out.write(line);
                }
            }
            exchange.sendResponseHeaders(202, -1);
            exchange.close();
        });
        server.start();
    }

    private static String quote(String value) {
        if (value == null) return "null";
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toCharArray()) {
            if (c == '"' || c == '\\') out.append('\\').append(c);
            else if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
            else out.append(c);
        }
        return out.append('"').toString();
    }
}
