import { useState } from "react";
import axiosInstance from "@/services/axios";
import { useAuth } from "@/services/AuthContext";
import {
  ThumbsUp,
  Flag,
  Building2,
  Download,
  FileText,
  Edit,
  Trash2,
  Star,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import BusinessReply from "./BusinessReply";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import AuthPrompt from "@/components/AuthPrompt";

interface Props {
  review: any;
  businessOwnerId?: number;
  onAction: () => void;
}

export default function ReviewItem({
  review,
  businessOwnerId,
  onAction,
}: Props) {
  const { isAuthenticated, user } = useAuth();
  const [reportOpen, setReportOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [authPromptOpen, setAuthPromptOpen] = useState(false);

  const vote = async (helpful: boolean) => {
    if (!isAuthenticated) {
      setAuthPromptOpen(true);
      return;
    }

    await axiosInstance.post("reviews/votes/", {
      owner: user?.id,
      review: review.id,
      is_helpful: helpful,
    });
    onAction();
  };

  const submitReport = async () => {
    if (!isAuthenticated) {
      setAuthPromptOpen(true);
      return;
    }
    if (!reason.trim()) return;

    await axiosInstance.post(`reviews/review/${review.id}/report/`, {
      reason,
    });
    setReportOpen(false);
    setReason("");
    toast("Report submitted successfully");
  };

  const isImage = (filename: string) => {
    const ext = filename.toLowerCase().split(".").pop();
    return ["jpg", "jpeg", "png", "gif", "webp", "svg"].includes(ext || "");
  };

  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(review.title);
  const [editBody, setEditBody] = useState(review.body);
  const [editRating, setEditRating] = useState(review.rating);

  const isAuthor = isAuthenticated && user?.id === review.author;

  const handleDelete = async () => {
    if (!confirm("Are you sure you want to delete this review?")) return;
    try {
      await axiosInstance.delete(`reviews/review/${review.id}/`);
      toast.success("Review deleted");
      onAction();
    } catch {
      toast.error("Failed to delete review");
    }
  };

  const handleUpdate = async () => {
    try {
      await axiosInstance.patch(`reviews/review/${review.id}/`, {
        title: editTitle,
        body: editBody,
        rating: editRating,
      });
      toast.success("Review updated");
      setIsEditing(false);
      onAction();
    } catch {
      toast.error("Failed to update review");
    }
  };

  const renderStars = (
    currentRating: number,
    setRating?: (r: number) => void
  ) => (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((s) => (
        <Star
          key={s}
          onClick={() => setRating && setRating(s)}
          className={`h-4 w-4 ${setRating ? "cursor-pointer" : ""} ${
            s <= currentRating
              ? "text-yellow-400 fill-yellow-400"
              : "text-gray-300"
          }`}
        />
      ))}
    </div>
  );

  if (isEditing) {
    return (
      <div className="border-b pb-4 last:border-none space-y-3">
        <div className="flex items-center gap-2">
          <Label>Rating:</Label>
          {renderStars(editRating, setEditRating)}
        </div>
        <Input
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          placeholder="Title"
        />
        <Textarea
          value={editBody}
          onChange={(e) => setEditBody(e.target.value)}
          placeholder="Review body"
          rows={4}
        />
        <div className="flex gap-2">
          <Button size="sm" onClick={handleUpdate}>
            Save
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setIsEditing(false)}
          >
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="border-b pb-4 last:border-none">
      <div className="flex justify-between items-start mb-2">
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 mb-1">
              <p className="font-medium">{review.title || "Untitled Review"}</p>
              {renderStars(review.rating)}
            </div>
            {isAuthor && (
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsEditing(true)}
                >
                  <Edit className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDelete}
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
          <p
            className="text-sm text-muted-foreground mb-2"
            dangerouslySetInnerHTML={{ __html: review.body }}
          />

          {review.attachments && review.attachments.length > 0 && (
            <div className="space-y-2 mb-3">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {review.attachments.map((att: any) => {
                  const fileName = att.file_name || "file";
                  const fileUrl = att.file_url || att.file;

                  if (isImage(fileName)) {
                    return (
                      <a
                        key={att.id}
                        href={fileUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block border rounded-lg overflow-hidden hover:shadow-lg transition-shadow"
                      >
                        <img
                          src={fileUrl}
                          alt={`Attachment ${att.id}`}
                          className="w-full h-32 object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).src =
                              'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Crect fill="%23ddd" width="100" height="100"/%3E%3Ctext fill="%23999" x="50%25" y="50%25" text-anchor="middle" dy=".3em"%3EImage%3C/text%3E%3C/svg%3E';
                          }}
                        />
                      </a>
                    );
                  }

                  return (
                    <a
                      key={att.id}
                      href={fileUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 p-3 border rounded-lg hover:bg-muted transition-colors"
                    >
                      <FileText className="h-5 w-5 text-muted-foreground" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs truncate">{fileName}</p>
                      </div>
                      <Download className="h-4 w-4 text-muted-foreground" />
                    </a>
                  );
                })}
              </div>
            </div>
          )}

          <div className="text-xs text-muted-foreground">
            By{" "}
            <Link
              to={`/user/${review.author_username || "unknown"}`}
              className="text-primary hover:underline"
            >
              {review.author_username || "Anonymous"}
            </Link>{" "}
            • {new Date(review.created_at).toLocaleDateString()}
          </div>
        </div>
      </div>

      {review.replies && review.replies.length > 0 && (
        <div className="ml-4 mt-3 space-y-2 border-l-2 border-muted pl-4">
          {review.replies.map((reply: any) => (
            <div key={reply.id} className="bg-muted/50 p-3 rounded-md">
              <div className="flex items-center gap-2 mb-1">
                <Building2 className="h-4 w-4 text-blue-600" />
                <span className="text-sm font-medium">Business Response</span>
              </div>
              <p className="text-sm">{reply.body}</p>
              <div className="text-xs text-muted-foreground mt-1">
                {new Date(reply.created_at).toLocaleDateString()}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 mt-3 text-sm text-muted-foreground">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => vote(true)}>
            <ThumbsUp className="h-4 w-4 mr-1" />
            Helpful
          </Button>
          {review.helpful_count > 0 && (
            <span>{review.helpful_count} found this helpful</span>
          )}
        </div>

        <Button
          variant="link"
          size="sm"
          className="text-destructive"
          onClick={() => {
            if (!isAuthenticated) {
              setAuthPromptOpen(true);
              return;
            }
            setReportOpen(true);
          }}
        >
          <Flag className="h-4 w-4 mr-1" />
          Report
        </Button>
        <Dialog open={reportOpen} onOpenChange={setReportOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Report Review</DialogTitle>
            </DialogHeader>
            <div className="grid gap-3 mt-2">
              <Label htmlFor="reason">Reason</Label>
              <Textarea
                id="reason"
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe why this review is inappropriate"
              />
              <Button onClick={submitReport}>Submit</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <BusinessReply
        reviewId={review.id}
        businessOwnerId={businessOwnerId || review.business?.owner}
        onReplyPosted={onAction}
      />
      <AuthPrompt open={authPromptOpen} onOpenChange={setAuthPromptOpen} />
    </div>
  );
}
