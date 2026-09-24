import { useState } from "react";
import axiosInstance from "@/services/axios";
import { useAuth } from "@/services/AuthContext";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Star, Upload, X } from "lucide-react";

interface ReviewProps {
  businessId: number;
  onReviewPosted: () => void;
  className?: string;
}

export default function WriteReview({
  businessId,
  onReviewPosted,
  className,
}: ReviewProps) {
  const { user, isAuthenticated } = useAuth();
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState(0);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setRating(0);
    setTitle("");
    setBody("");
    setFiles([]);
    setError(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const submitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isAuthenticated || !user) return;

    if (rating === 0) {
      setError("Please select a star rating");
      return;
    }

    setLoading(true);

    try {
      // Create review first
      const reviewRes = await axiosInstance.post("reviews/review/", {
        business: businessId,
        rating,
        title,
        body,
        author: user.id,
      });

      // Upload attachments if any
      if (files.length > 0) {
        for (const file of files) {
          const formData = new FormData();
          formData.append("file", file);
          formData.append("review", reviewRes.data.id);

          await axiosInstance.post("reviews/attachments/", formData, {
            headers: { "Content-Type": "multipart/form-data" },
          });
        }
      }

      reset();
      setOpen(false);
      onReviewPosted();
    } catch {
      setError("Failed to submit review. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const renderStars = () => (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((s) => (
        <Star
          key={s}
          onClick={() => setRating(s)}
          className={`h-5 w-5 cursor-pointer ${
            s <= rating ? "text-yellow-400 fill-yellow-400" : "text-gray-300"
          }`}
        />
      ))}
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          onClick={() =>
            !isAuthenticated && alert("Please log in to post a review.")
          }
          className={className}
        >
          Write a Review
        </Button>
      </DialogTrigger>
      {isAuthenticated && (
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Write a Review</DialogTitle>
          </DialogHeader>
          <form onSubmit={submitReview} className="space-y-4 mt-2">
            <div className="flex items-center gap-2">
              <Label className="text-sm font-medium">Rating:</Label>
              {renderStars()}
            </div>

            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Short summary of your experience"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="body">Review</Label>
              <Textarea
                id="body"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={4}
                placeholder="Write your detailed feedback..."
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="files">Attachments (Optional)</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="files"
                  type="file"
                  multiple
                  onChange={handleFileChange}
                  className="hidden"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => document.getElementById("files")?.click()}
                >
                  <Upload className="h-4 w-4 mr-2" />
                  Choose Files
                </Button>
                <span className="text-sm text-muted-foreground">
                  {files.length} file(s) selected
                </span>
              </div>
              {files.length > 0 && (
                <div className="space-y-1">
                  {files.map((file, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-sm bg-muted p-2 rounded"
                    >
                      <span className="truncate">{file.name}</span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFile(idx)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {error && <p className="text-destructive text-sm">{error}</p>}

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Submitting..." : "Submit Review"}
            </Button>
          </form>
        </DialogContent>
      )}
    </Dialog>
  );
}
