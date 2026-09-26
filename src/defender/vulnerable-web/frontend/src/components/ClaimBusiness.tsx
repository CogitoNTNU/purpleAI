import { useState, useEffect } from "react";
import axiosInstance from "@/services/axios";
import { useAuth } from "@/services/AuthContext";
import { Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

interface Props {
  businessId: number;
}

export default function ClaimBusiness({ businessId }: Props) {
  const { isAuthenticated } = useAuth();
  const [open, setOpen] = useState(false);
  const [statement, setStatement] = useState("");
  const [alreadyClaimed, setAlreadyClaimed] = useState(false);

  useEffect(() => {
    const fetchClaims = async () => {
      if (!isAuthenticated) return;
      const res = await axiosInstance.get("businesses/claims/");
      const existing = (res.data || []).some(
        (c: any) => c.business === businessId && c.status === "pending"
      );
      setAlreadyClaimed(existing);
    };
    fetchClaims();
  }, [isAuthenticated, businessId]);

  const handleClaim = async () => {
    await axiosInstance.post("businesses/claims/", {
      business: businessId,
      statement,
    });
    toast("Claim submitted successfully!", {
      description: "An administrator will review your claim shortly",
    });
    setStatement("");
    setOpen(false);
    setAlreadyClaimed(true);
  };

  if (alreadyClaimed || !isAuthenticated) return null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="flex gap-1">
          <Building2 className="h-4 w-4" />
          Claim Business
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Claim this Business</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <Label>Your statement</Label>
          <Textarea
            rows={4}
            value={statement}
            placeholder="Explain you're the rightful owner or manager..."
            onChange={(e) => setStatement(e.target.value)}
          />
          <Button onClick={handleClaim}>Submit Claim</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
