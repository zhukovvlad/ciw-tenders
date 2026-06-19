import { FileSpreadsheet, Loader2, Upload } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, type MatchResult } from "@/lib/api"

function statusVariant(status: string): "success" | "warning" | "destructive" {
  if (status.startsWith("Уверенное")) return "success"
  if (status.startsWith("Требует")) return "warning"
  return "destructive"
}

export function EstimatePage() {
  const [file, setFile] = useState<File | null>(null)
  const [results, setResults] = useState<MatchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) return
    setLoading(true)
    setError(null)
    setResults([])
    try {
      setResults(await api.matchEstimate(file))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Загрузка сметы</CardTitle>
          <CardDescription>
            Excel-файл. Обрабатываются строки с «Вид раздела» = «СМР» и сопоставляются со справочником.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-3">
            <Input
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="max-w-sm"
            />
            <Button type="submit" disabled={!file || loading}>
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Upload className="size-4" />
              )}
              Сопоставить
            </Button>
            {file && (
              <span className="flex items-center gap-1 text-sm text-muted-foreground">
                <FileSpreadsheet className="size-4" /> {file.name}
              </span>
            )}
          </form>
          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Результаты
              <Badge variant="secondary">{results.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[60px]">Строка</TableHead>
                  <TableHead>Работа из сметы</TableHead>
                  <TableHead>Сопоставленная статья</TableHead>
                  <TableHead className="w-[90px]">Score</TableHead>
                  <TableHead className="w-[180px]">Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map((r) => (
                  <TableRow key={r.row_number}>
                    <TableCell className="text-muted-foreground">{r.row_number}</TableCell>
                    <TableCell>{r.source_name}</TableCell>
                    <TableCell>
                      {r.matched_name ? (
                        <span>
                          <span className="font-mono text-xs text-muted-foreground">
                            {r.matched_code}
                          </span>{" "}
                          {r.matched_name}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono">{r.score.toFixed(2)}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(r.status)}>{r.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export default EstimatePage
